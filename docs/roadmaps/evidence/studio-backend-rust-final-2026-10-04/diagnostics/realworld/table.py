"""Print the real-world comparison as Markdown rows: one column per group of runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import describe, load  # noqa: E402

RESULTS = Path(sys.argv[1])
GROUPS: list[tuple[str, list[str]]] = []
for argument in sys.argv[2:]:
    title, jobs = argument.split("=", 1)
    GROUPS.append((title, jobs.split(",")))


def runs(jobs: list[str]) -> list[dict]:
    found = []
    for job in jobs:
        loaded = load(RESULTS, "rw", job)
        if loaded is not None:
            found.append(describe(*loaded))
    return found


def cells(values: list, unit: str = "", digits: int = 0) -> str:
    if not values:
        return "—"
    def text(value):
        if value is None:
            return "—"
        if isinstance(value, float) and digits:
            return f"{value:,.{digits}f}"
        if isinstance(value, (int, float)):
            return f"{round(value):,}"
        return str(value)
    return ", ".join(text(value) for value in values) + (f" {unit}" if unit else "")


def seconds(values: list) -> str:
    return ", ".join("—" if v is None else f"{v / 1000:.2f}" for v in values) + " s"


data = [(title, runs(jobs)) for title, jobs in GROUPS]
print("| | " + " | ".join(title for title, _ in data) + " |")
print("| --- | " + " | ".join("---:" for _ in data) + " |")


def row(label: str, getter) -> None:
    print(f"| {label} | " + " | ".join(getter(group) for _, group in data) + " |")


row("Runs", lambda g: str(len(g)))
row("Page loads completed", lambda g: cells([r["page_actions"] for r in g]))
row(
    "API responses that were 5xx",
    lambda g: ", ".join(f"{r['api_5xx']} of {r['api_total']:,}" for r in g),
)
row("Queries run again after a snapshot change", lambda g: cells([r["snapshot_reruns"] for r in g]))
for action, label in [
    ("traces list, all", "Traces list"),
    ("traces list, has LLM (default view)", "Traces list, default view"),
    ("workflow list", "Workflow list"),
    ("trace detail", "Trace detail"),
    ("services list", "Services list"),
]:
    row(f"{label}: p50", lambda g, a=action: cells([r["pages"][a]["p50_ms"] for r in g], "ms"))
    row(f"{label}: p95", lambda g, a=action: cells([r["pages"][a]["p95_ms"] for r in g], "ms"))
row(
    "Pages that showed an error",
    lambda g: cells([sum(o.get("error", 0) for o in r["pages_not_rows"].values()) for r in g]),
)
row(
    "Default traces view that came back empty",
    lambda g: ", ".join(
        f"{r['pages']['traces list, has LLM (default view)']['outcomes'].get('empty', 0)} of "
        f"{r['pages']['traces list, has LLM (default view)']['n']}"
        for r in g
    ),
)
row("Session check on each page load: p95", lambda g: cells([r["api"]["/api/v1/auth-test"]["p95_ms"] for r in g], "ms"))
row("Real SDK runs shown in Studio", lambda g: ", ".join(f"{r['sdk_runs'] - r['sdk_failed']} of {r['sdk_runs']}" for r in g))
row(
    "Real SDK run to visible in Studio",
    lambda g: ", ".join(f"{min(r['sdk_to_studio_s']):.1f}–{max(r['sdk_to_studio_s']):.1f}" for r in g) + " s",
)
row(
    "Browser proof of that run",
    lambda g: ", ".join(f"{min(r['browser_proof_s']):.1f}–{max(r['browser_proof_s']):.1f}" for r in g) + " s",
)
row("Accepted span to readable: p50", lambda g: cells([r["freshness_p50_ms"] for r in g], "ms"))
row("Accepted span to readable: p95", lambda g: cells([r["freshness_p95_ms"] for r in g], "ms"))
row("Accepted span to readable: slowest", lambda g: cells([r["freshness_max_ms"] for r in g], "ms"))
row("Backend cgroup peak", lambda g: cells([r["backend_peak_mib"] for r in g], "MiB"))
row("Backend process RSS", lambda g: cells([r["backend_rss_mib"] for r in g], "MiB"))
row("Backend CPU", lambda g: cells([r["backend_cpu_s"] for r in g], "s", 1))
row("Ingestion CPU", lambda g: cells([r["ingestion_cpu_s"] for r in g], "s", 1))
row("Spans acknowledged", lambda g: cells([r["spans_acknowledged"] for r in g]))
row("Exports refused once and retried", lambda g: cells([r["exports_refused_once"] for r in g]))
row("Exports that failed after retries", lambda g: cells([r["exports_failed"] for r in g]))
row("Export p95", lambda g: cells([r["export_p95_ms"] for r in g], "ms", 1))
row("Export p99", lambda g: cells([r["export_p99_ms"] for r in g], "ms", 1))
