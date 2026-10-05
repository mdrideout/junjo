#!/usr/bin/env python3
"""Print real-world runs side by side as a Markdown table.

Each argument is one column: a title and the result files of its runs.

    python real_world_report.py baseline=a1.json,a2.json candidate=b1.json,b2.json

A cell lists one value per run, in the order the files were given. The table
reports what was measured. It sets no thresholds: the reader compares the
columns.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MIB = 2**20
# The pages the browser tabs load, in the order they load them.
PAGES = ("services", "traces, default view", "traces, all", "trace detail", "workflows")
# Loaded only with --history-pages.
HISTORY_PAGES = ("agents", "agents, no match", "execution link")
# Loaded only with --api-key-filter.
KEY_FILTER_PAGES = ("traces, one key",)
SESSION_CHECK_ROUTE = "/api/v1/auth-test"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def default_view_comparisons(actions: list[dict[str, Any]]) -> list[bool]:
    """Whether each default Traces view showed fewer traces than the full list.

    A tab loads the Traces page with "Has LLM Spans" checked and then clears
    the filter. Every trace the exporters send has LLM spans, so both lists
    hold the same traces, and a shorter default view is missing some. Each
    default view is compared with the full list the same tab loaded next.
    """
    comparisons = []
    last_default_view: dict[int, dict[str, Any]] = {}
    for action in actions:
        if action["action"] == "traces, default view":
            last_default_view[action["tab"]] = action
        elif action["action"] == "traces, all" and action["outcome"] == "rows":
            default_view = last_default_view.pop(action["tab"], None)
            if default_view is not None and default_view["outcome"] != "error":
                comparisons.append(default_view["rows"] < action["rows"])
    return comparisons


def describe(result: dict[str, Any]) -> dict[str, Any]:
    """The numbers of one run that the table shows."""
    exports = result["exports"]
    before, after = result["container_before"], result["container_after"]
    activity = result["side_activity"].get("output", {})
    browser = activity.get("browser", {})
    actions = browser.get("actions", [])
    responses = browser.get("responses", [])
    sdk_runs = activity.get("sdk_runs", [])
    probes = result["freshness"]
    readable = [
        probe["readable_ms"] for probe in probes if probe["readable_ms"] is not None
    ]
    session_checks = [
        response["ms"]
        for response in responses
        if response["route"] == SESSION_CHECK_ROUTE
    ]

    pages = {}
    for page in PAGES + HISTORY_PAGES + KEY_FILTER_PAGES:
        loads = [action for action in actions if action["action"] == page]
        pages[page] = {
            "loads": len(loads),
            "empty": sum(action["outcome"] == "empty" for action in loads),
            "p50_ms": percentile([action["ms"] for action in loads], 0.50),
            "p95_ms": percentile([action["ms"] for action in loads], 0.95),
        }

    default_view_short = default_view_comparisons(actions)
    described = {
        "checks_passed": all(result["acceptance"].values()),
        "default_views_compared": len(default_view_short),
        "default_views_short": sum(default_view_short),
        "spans_acknowledged": exports["acknowledged_spans"],
        "exports_refused_once": exports["attempt_codes"].get("UNAVAILABLE", 0),
        "exports_failed": exports["requested"] - exports["successful"],
        "export_p95_ms": exports["p95_ms"],
        "export_p99_ms": exports["p99_ms"],
        "page_loads": len(actions),
        "pages": pages,
        "pages_with_error": sum(action["outcome"] == "error" for action in actions),
        "pages_not_settled": sum(
            action["outcome"] in ("timeout", "exception") for action in actions
        ),
        "api_responses": len(responses),
        "api_5xx": sum(response["status"] >= 500 for response in responses),
        "requests_failed": len(browser.get("requestFailures", [])),
        "session_check_p95_ms": percentile(session_checks, 0.95),
        "sdk_runs": len(sdk_runs),
        "sdk_runs_shown": sum(
            run.get("browser_proof_exit_code") == 0 for run in sdk_runs
        ),
        "sdk_to_studio_seconds": [
            run["sdk_to_studio_seconds"]
            for run in sdk_runs
            if run["sdk_to_studio_exit_code"] == 0
        ],
        "browser_proof_seconds": [
            run["browser_proof_seconds"]
            for run in sdk_runs
            if run.get("browser_proof_exit_code") == 0
        ],
        "probes": len(probes),
        "probes_never_readable": sum(
            probe["export_code"] == "OK" and probe["readable_ms"] is None
            for probe in probes
        ),
        "readable_p50_ms": percentile(readable, 0.50),
        "readable_p95_ms": percentile(readable, 0.95),
        "readable_slowest_ms": max(readable, default=None),
    }
    for service in ("backend", "ingestion"):
        described[f"{service}_cpu_seconds"] = (
            after[service]["cpu_usage_seconds"] - before[service]["cpu_usage_seconds"]
        )
        described[f"{service}_peak_memory_mib"] = (
            after[service]["peak_cgroup_memory_bytes"] / MIB
        )
    return described


def number(value: float | None, digits: int = 0) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def span(values: list[float]) -> str:
    return f"{min(values):.1f}–{max(values):.1f}" if values else "—"


def rows(runs: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Every row of one column: its label and its cell."""

    def each(render) -> str:
        return ", ".join(render(run) for run in runs)

    table = [
        ("Runs", str(len(runs))),
        (
            "Runs that passed the harness checks",
            f"{sum(run['checks_passed'] for run in runs)} of {len(runs)}",
        ),
        ("Page loads completed", each(lambda run: number(run["page_loads"]))),
        (
            "API responses that were 5xx",
            each(lambda run: f"{run['api_5xx']} of {run['api_responses']:,}"),
        ),
        ("Requests that failed", each(lambda run: number(run["requests_failed"]))),
        (
            "Pages that showed an error",
            each(lambda run: number(run["pages_with_error"])),
        ),
        (
            "Pages that did not settle",
            each(lambda run: number(run["pages_not_settled"])),
        ),
    ]
    for page in PAGES:
        table.append(
            (
                f"Page “{page}”: p50 ms",
                each(lambda run, page=page: number(run["pages"][page]["p50_ms"])),
            )
        )
        table.append(
            (
                f"Page “{page}”: p95 ms",
                each(lambda run, page=page: number(run["pages"][page]["p95_ms"])),
            )
        )
    for page in HISTORY_PAGES + KEY_FILTER_PAGES:
        if not any(run["pages"][page]["loads"] for run in runs):
            continue
        table.append(
            (
                f"Page “{page}”: p50 ms",
                each(lambda run, page=page: number(run["pages"][page]["p50_ms"])),
            )
        )
        table.append(
            (
                f"Page “{page}”: p95 ms",
                each(lambda run, page=page: number(run["pages"][page]["p95_ms"])),
            )
        )
    default_view = "traces, default view"
    table += [
        (
            "Default Traces view that came back empty",
            each(
                lambda run: (
                    f"{run['pages'][default_view]['empty']} of "
                    f"{run['pages'][default_view]['loads']}"
                )
            ),
        ),
        (
            "Default Traces view with fewer traces than the full list",
            each(
                lambda run: (
                    f"{run['default_views_short']} of {run['default_views_compared']}"
                )
            ),
        ),
        (
            "Session check on each page load: p95 ms",
            each(lambda run: number(run["session_check_p95_ms"])),
        ),
        (
            "SDK runs shown in Studio",
            each(lambda run: f"{run['sdk_runs_shown']} of {run['sdk_runs']}"),
        ),
        (
            "SDK run to shown by Studio's APIs: seconds",
            each(lambda run: span(run["sdk_to_studio_seconds"])),
        ),
        (
            "SDK run found in the browser: seconds",
            each(lambda run: span(run["browser_proof_seconds"])),
        ),
        (
            "Accepted trace to readable: p50 ms",
            each(lambda run: number(run["readable_p50_ms"])),
        ),
        (
            "Accepted trace to readable: p95 ms",
            each(lambda run: number(run["readable_p95_ms"])),
        ),
        (
            "Accepted trace to readable: slowest ms",
            each(lambda run: number(run["readable_slowest_ms"])),
        ),
        (
            "Probe traces never readable",
            each(lambda run: f"{run['probes_never_readable']} of {run['probes']}"),
        ),
        ("Spans acknowledged", each(lambda run: number(run["spans_acknowledged"]))),
        (
            "Exports refused once and retried",
            each(lambda run: number(run["exports_refused_once"])),
        ),
        (
            "Exports that failed after retries",
            each(lambda run: number(run["exports_failed"])),
        ),
        ("Export p95 ms", each(lambda run: number(run["export_p95_ms"], 1))),
        ("Export p99 ms", each(lambda run: number(run["export_p99_ms"], 1))),
        (
            "Backend CPU seconds",
            each(lambda run: number(run["backend_cpu_seconds"], 1)),
        ),
        (
            "Ingestion CPU seconds",
            each(lambda run: number(run["ingestion_cpu_seconds"], 1)),
        ),
        (
            "Backend peak memory MiB",
            each(lambda run: number(run["backend_peak_memory_mib"])),
        ),
        (
            "Ingestion peak memory MiB",
            each(lambda run: number(run["ingestion_peak_memory_mib"])),
        ),
    ]
    return table


def markdown(columns: list[tuple[str, list[dict[str, Any]]]]) -> str:
    """One Markdown table: a column per title, a row per measurement."""
    cells = [rows(runs) for _, runs in columns]
    lines = [
        "| | " + " | ".join(title for title, _ in columns) + " |",
        "| --- | " + " | ".join("---:" for _ in columns) + " |",
    ]
    for index, (label, _) in enumerate(cells[0]):
        lines.append(
            f"| {label} | " + " | ".join(column[index][1] for column in cells) + " |"
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    columns = []
    for argument in sys.argv[1:]:
        title, _, files = argument.partition("=")
        runs = [
            describe(json.loads(Path(file).read_text(encoding="utf-8")))
            for file in files.split(",")
        ]
        columns.append((title, runs))
    print(markdown(columns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
