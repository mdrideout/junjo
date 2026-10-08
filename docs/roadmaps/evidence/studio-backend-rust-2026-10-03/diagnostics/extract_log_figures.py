"""Record the figures the README reads from service logs.

Service logs match the repository's `*.log` ignore rule, so they stay local.
This writes the few values taken from them to log-derived.json, which is
tracked.
"""
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent.parent
RESULTS = EVIDENCE / "results"


def json_lines(name: str, service: str):
    for line in (RESULTS / f"{name}.services.log").read_text().splitlines():
        prefix, _, payload = line.partition("| ")
        if not prefix.startswith(service) or not payload.startswith("{"):
            continue
        try:
            yield json.loads(payload)
        except ValueError:
            continue


def memory_floor(name: str) -> list[dict]:
    stages = []
    for record in json_lines(name, "backend"):
        fields = record.get("fields", {})
        if fields.get("message") == "resident memory":
            stages.append({key: fields[key] for key in ("stage", "rss_kib", "rss_anon_kib", "rss_file_kib", "threads")})
    return stages


def snapshot_counts(name: str) -> dict:
    messages = [record.get("fields", {}).get("message") for record in json_lines(name, "ingestion")]
    return {
        "hot_snapshot_builds": messages.count("Created hot Parquet snapshot (streaming)"),
        "prepare_hot_snapshot_calls": messages.count("PrepareHotSnapshot completed"),
    }


out = {
    "rust_memory_floor": {"run": "load-rust-floor-mixed-1", "stages": memory_floor("load-rust-floor-mixed-1")},
    "hot_snapshots": {
        name: snapshot_counts(name)
        for name in ("diag-python-inglog-mixed-1", "diag-rust-system-inglog-mixed-1")
    },
}
(EVIDENCE / "log-derived.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
