"""Failure cases that must never produce a green delivery benchmark."""

import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from auth_path_benchmark import export_worker
from compare_results import compare
from delivery import verify_delivery, workload_trace_id


def write_batch(path, trace_id, span_ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    batch = pa.record_batch(
        {
            "trace_id": [trace_id] * len(span_ids),
            "span_id": [value.to_bytes(8, "big").hex() for value in span_ids],
        }
    )
    if path.suffix == ".ipc":
        with (
            pa.OSFile(str(path), "wb") as sink,
            pa.ipc.new_stream(sink, batch.schema) as writer,
        ):
            writer.write_batch(batch)
    else:
        pq.write_table(pa.Table.from_batches([batch]), path)


def test_duplicates_and_snapshots_cannot_mask_missing_acknowledged_spans(tmp_path):
    trace_id = workload_trace_id(0, 0).hex()
    write_batch(tmp_path / "spans/wal/one.ipc", trace_id, [1, 1])
    write_batch(tmp_path / "spans/hot_snapshot.parquet", trace_id, [1, 2])
    result = verify_delivery(tmp_path, {trace_id: 2})
    assert result["missing_acknowledged_spans"] == 1
    assert result["duplicate_rows"] == 1
    assert not result["all_acknowledged_spans_persisted"]


def test_counts_canonical_hot_and_cold_without_counting_other_exports(tmp_path):
    trace_id = workload_trace_id(0, 0).hex()
    other_id = workload_trace_id(0, 1).hex()
    write_batch(tmp_path / "spans/wal/one.ipc", trace_id, [1])
    write_batch(tmp_path / "spans/parquet/day/two.parquet", trace_id, [2])
    write_batch(tmp_path / "spans/wal/other.ipc", other_id, [1])
    result = verify_delivery(tmp_path, {trace_id: 2})
    assert result["persisted_acknowledged_spans"] == 2
    assert result["unacknowledged_rows"] == 1
    assert result["all_acknowledged_spans_persisted"]


@pytest.mark.asyncio
async def test_partial_success_is_not_counted_as_successful_delivery():
    config = SimpleNamespace(
        spans_per_export=2,
        exporters=1,
        exports_per_exporter=1,
        export_interval_ms=0,
        timing="synchronized",
        cadence_mode="start-to-start",
        max_retries=0,
    )
    response = SimpleNamespace(
        HasField=lambda _: True, partial_success=SimpleNamespace(rejected_spans=1)
    )
    stub = SimpleNamespace(Export=AsyncMock(return_value=response))
    channel = AsyncMock()
    start = asyncio.Event()
    start.set()
    attempts, final, acknowledged = Counter(), Counter(), {}
    with (
        patch("auth_path_benchmark.grpc.aio.insecure_channel", return_value=channel),
        patch(
            "auth_path_benchmark.trace_service_pb2_grpc.TraceServiceStub",
            return_value=stub,
        ),
    ):
        await export_worker(
            0,
            config,
            "synthetic-key",
            "unused",
            start,
            [],
            attempts,
            final,
            None,
            acknowledged,
        )
    assert final == {"PARTIAL_SUCCESS": 1}
    assert not acknowledged


def test_comparison_refuses_failed_runs_even_if_they_report_high_throughput():
    failed = {"config": {}, "acceptance": {"all_exports_succeeded": False}}
    with pytest.raises(ValueError, match="failed benchmark checks"):
        compare([failed], [failed])


def test_comparison_refuses_unverified_delivery():
    unverified = {
        "config": {"verify_delivery": False},
        "constraints": {},
        "acceptance": {"all_exports_succeeded": True},
    }
    with pytest.raises(ValueError, match="verified delivery is required"):
        compare([unverified], [unverified])
