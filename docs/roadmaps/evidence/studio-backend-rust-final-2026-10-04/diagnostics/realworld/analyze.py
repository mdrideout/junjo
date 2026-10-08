"""Summarize real-world runs: one block per run, then medians per variant.

Usage: analyze.py <results-dir> <prefix> <variant>:<shape>:<rep> ...
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

MIB = 2**20


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))]


def load(results: Path, prefix: str, job: str) -> tuple[str, dict, str] | None:
    variant, shape, rep = job.split(":")
    name = f"{prefix}-{variant}-{shape}-{rep}"
    path = results / f"{name}.json"
    if not path.is_file():
        return None
    log = results / f"{name}.services.log"
    return name, json.loads(path.read_text()), log.read_text(errors="replace") if log.is_file() else ""


def describe(name: str, data: dict, log: str) -> dict:
    real = data["real_world"]
    exports = data["exports"]
    phase = data["ingestion_phase"]
    out: dict = {"name": name}
    out["accepted"] = all(data["acceptance"].values())
    out["not_accepted"] = [key for key, value in data["acceptance"].items() if not value]
    out["spans_acknowledged"] = exports["acknowledged_spans"]
    out["export_p95_ms"] = round(exports["p95_ms"], 1)
    out["export_p99_ms"] = round(exports["p99_ms"], 1)
    out["exports_refused_once"] = exports["attempt_codes"].get("UNAVAILABLE", 0)
    out["exports_failed"] = sum(v for k, v in exports["final_codes"].items() if k != "OK")
    out["backend_cpu_s"] = round(phase["containers"]["backend"]["cpu_usage_seconds"], 2)
    out["ingestion_cpu_s"] = round(phase["containers"]["ingestion"]["cpu_usage_seconds"], 2)
    out["backend_peak_mib"] = round(phase["memory"]["backend"]["memory_peak_bytes"] / MIB)
    out["backend_rss_mib"] = round(phase["memory"]["backend"]["process_rss_kib"] / 1024)
    out["backend_memory_events"] = {k: v for k, v in phase["memory"]["backend"]["events"].items() if v}

    pages = real.get("pages") or {}
    out["pages"] = {
        action: {
            "n": page["count"],
            "outcomes": page["outcomes"],
            "p50_ms": page["p50_ms"],
            "p95_ms": page["p95_ms"],
            "max_ms": page["max_ms"],
        }
        for action, page in pages.items()
    }
    api = real.get("api") or {}
    out["api"] = {
        family: {
            "n": item["count"],
            "statuses": item["statuses"],
            "p50_ms": item["p50_ms"],
            "p95_ms": item["p95_ms"],
            "p99_ms": item["p99_ms"],
        }
        for family, item in api.items()
    }
    out["api_total"] = sum(item["count"] for item in api.values())
    out["api_5xx"] = sum(
        count for item in api.values() for status, count in item["statuses"].items() if status.startswith("5")
    )
    out["request_failures"] = len(real.get("request_failures") or [])
    out["page_errors"] = len(real.get("page_errors") or [])
    out["page_actions"] = sum(page["count"] for page in pages.values())
    out["pages_not_rows"] = {
        action: {k: v for k, v in page["outcomes"].items() if k != "rows"}
        for action, page in pages.items()
        if any(k != "rows" for k in page["outcomes"])
    }

    sdk = real.get("sdk_runs") or []
    out["sdk_runs"] = len(sdk)
    out["sdk_failed"] = sum(
        1 for run in sdk if run.get("sdk_to_studio_exit") != 0 or run.get("browser_proof_exit") != 0
    )
    out["sdk_to_studio_s"] = [run.get("sdk_to_studio_seconds") for run in sdk]
    out["browser_proof_s"] = [run.get("browser_proof_seconds") for run in sdk]
    out["sdk_failure_output"] = [
        (run.get("sdk_to_studio_output") or run.get("browser_proof_output") or "")[-300:]
        for run in sdk
        if run.get("sdk_to_studio_exit") != 0 or run.get("browser_proof_exit") != 0
    ]

    fresh = real.get("freshness") or []
    visible = [item["visible_ms"] for item in fresh if item["visible_ms"] is not None]
    out["freshness_probes"] = len(fresh)
    out["freshness_not_visible"] = sum(
        1 for item in fresh if item["export_code"] == "OK" and item["visible_ms"] is None
    )
    out["freshness_not_exported"] = sum(1 for item in fresh if item["export_code"] != "OK")
    out["freshness_p50_ms"] = round(percentile(visible, 0.5)) if visible else None
    out["freshness_p95_ms"] = round(percentile(visible, 0.95)) if visible else None
    out["freshness_max_ms"] = round(max(visible)) if visible else None
    out["freshness_poll_errors"] = dict(
        Counter(code for item in fresh for code, count in item["codes"].items() if code != "200" for _ in range(count))
    )

    errors = re.findall(r'"level":"ERROR","fields":\{"message":"([^"]*)","error":"([^"]{0,60})', log)
    out["backend_error_lines"] = dict(Counter(f"{message}: {error}" for message, error in errors))
    out["snapshot_reruns"] = log.count("the hot snapshot changed while it was read")
    return out


def main() -> None:
    results = Path(sys.argv[1])
    prefix = sys.argv[2]
    by_variant: dict[str, list[dict]] = {}
    for job in sys.argv[3:]:
        loaded = load(results, prefix, job)
        if loaded is None:
            print(f"== {job}: missing")
            continue
        summary = describe(*loaded)
        by_variant.setdefault(job.split(":")[0], []).append(summary)
        print(f"== {summary['name']}  accepted={summary['accepted']} {summary['not_accepted'] or ''}")
        print(
            f"   ingestion: {summary['spans_acknowledged']} spans, export p95 {summary['export_p95_ms']} ms,"
            f" p99 {summary['export_p99_ms']} ms, refused once {summary['exports_refused_once']},"
            f" failed {summary['exports_failed']}, ingestion CPU {summary['ingestion_cpu_s']} s"
        )
        print(
            f"   backend: CPU {summary['backend_cpu_s']} s, cgroup peak {summary['backend_peak_mib']} MiB,"
            f" RSS {summary['backend_rss_mib']} MiB, memory events {summary['backend_memory_events']}"
        )
        print(
            f"   browser: {summary['page_actions']} page actions, {summary['api_total']} API responses,"
            f" {summary['api_5xx']} server errors, {summary['request_failures']} failed requests,"
            f" {summary['page_errors']} page errors; not showing rows: {summary['pages_not_rows']}"
        )
        for action, page in summary["pages"].items():
            print(f"     page {action}: n={page['n']} p50={page['p50_ms']} p95={page['p95_ms']} max={page['max_ms']} {page['outcomes']}")
        for family, item in summary["api"].items():
            if family.endswith("auth-test") or family.endswith("db-has-users"):
                continue
            print(f"     api  {family}: n={item['n']} p50={item['p50_ms']} p95={item['p95_ms']} p99={item['p99_ms']} {item['statuses']}")
        auth = summary["api"].get("/api/v1/auth-test")
        if auth:
            print(f"     api  /api/v1/auth-test: n={auth['n']} p50={auth['p50_ms']} p95={auth['p95_ms']} p99={auth['p99_ms']} {auth['statuses']}")
        print(
            f"   real SDK: {summary['sdk_runs']} runs, {summary['sdk_failed']} failed,"
            f" SDK to Studio {summary['sdk_to_studio_s']} s, browser proof {summary['browser_proof_s']} s"
        )
        for text in summary["sdk_failure_output"]:
            print(f"     FAILURE: {text!r}")
        print(
            f"   freshness: {summary['freshness_probes']} probes, p50 {summary['freshness_p50_ms']} ms,"
            f" p95 {summary['freshness_p95_ms']} ms, max {summary['freshness_max_ms']} ms,"
            f" not visible {summary['freshness_not_visible']}, not exported {summary['freshness_not_exported']},"
            f" poll errors {summary['freshness_poll_errors']}"
        )
        print(f"   backend error lines: {summary['backend_error_lines']}  snapshot reruns: {summary['snapshot_reruns']}")
    Path(results / f"{prefix}-summary.json").write_text(json.dumps(by_variant, indent=1))


if __name__ == "__main__":
    main()
