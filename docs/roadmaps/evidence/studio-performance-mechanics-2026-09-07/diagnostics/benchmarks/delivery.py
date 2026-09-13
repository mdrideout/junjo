"""Verify identified benchmark spans in canonical storage after services stop."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def workload_trace_id(exporter_id: int, export_index: int) -> bytes:
    return (
        (exporter_id + 1).to_bytes(4, "big")
        + (export_index + 1).to_bytes(8, "big")
        + b"jnjb"
    )


def verify_delivery(data_path: Path, acknowledged: dict[str, int]) -> dict:
    # One bit per span identity avoids retaining millions of Python tuples.
    seen: dict[str, int] = {}
    duplicate_rows = 0
    unacknowledged_rows = 0
    canonical_rows = 0
    rows_by_tier = {"wal": 0, "parquet": 0}
    files_by_tier = {"wal": 0, "parquet": 0}
    files = sorted((data_path / "spans" / "wal").glob("*.ipc"))
    files += sorted((data_path / "spans" / "parquet").rglob("*.parquet"))
    for path in files:
        tier = "wal" if path.suffix == ".ipc" else "parquet"
        files_by_tier[tier] += 1
        with pa.memory_map(str(path), "r") as source:
            if path.suffix == ".ipc":
                batches = pa.ipc.open_stream(source)
            else:
                batches = pq.ParquetFile(source).iter_batches(
                    columns=["trace_id", "span_id"]
                )
            for batch in batches:
                for trace_id, span_id in zip(
                    batch.column("trace_id").to_pylist(),
                    batch.column("span_id").to_pylist(),
                    strict=True,
                ):
                    if not trace_id.endswith(b"jnjb".hex()):
                        continue
                    canonical_rows += 1
                    rows_by_tier[tier] += 1
                    expected = acknowledged.get(trace_id)
                    if expected is None:
                        unacknowledged_rows += 1
                        continue
                    index = int(span_id, 16) - 1
                    if not 0 <= index < expected:
                        raise ValueError(
                            f"unexpected span identity for acknowledged export: {trace_id}/{span_id}"
                        )
                    bit = 1 << index
                    previous = seen.get(trace_id, 0)
                    duplicate_rows += bool(previous & bit)
                    seen[trace_id] = previous | bit
    acknowledged_spans = sum(acknowledged.values())
    persisted = sum(bits.bit_count() for bits in seen.values())
    return {
        "acknowledged_spans": acknowledged_spans,
        "persisted_acknowledged_spans": persisted,
        "missing_acknowledged_spans": acknowledged_spans - persisted,
        "duplicate_rows": duplicate_rows,
        "unacknowledged_rows": unacknowledged_rows,
        "canonical_workload_rows": canonical_rows,
        "canonical_files": len(files),
        "rows_by_tier": rows_by_tier,
        "files_by_tier": files_by_tier,
        "all_acknowledged_spans_persisted": persisted == acknowledged_spans,
    }
