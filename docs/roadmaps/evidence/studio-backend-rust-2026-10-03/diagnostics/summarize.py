"""Print one comparable line-set per result file."""
import json
import sys
from pathlib import Path

MIB = 1024 * 1024


def summarize(path: Path) -> dict:
    r = json.loads(path.read_text())
    before, after = r["container_before"], r["container_after"]
    phase = r["ingestion_phase"]
    idle = r["idle"]["memory"] if r.get("idle") else None
    out = {
        "label": r["config"]["implementation_label"],
        "accepted": all(r["acceptance"].values()),
        "failed_checks": [k for k, v in r["acceptance"].items() if not v],
        "offered_spans": r["exports"]["offered_spans"],
        "acknowledged_spans": r["exports"]["acknowledged_spans"],
        "persisted_spans": r.get("delivery", {}).get("persisted_acknowledged_spans"),
        "indexed_rows": r["indexing"].get("indexed_rows"),
        "completed_queries": sum(r["queries"]["result_codes"].values()),
        "query_codes": r["queries"]["result_codes"],
        "spans_per_second": round(r["exports"]["spans_per_second"]),
        "export_p95_ms": round(r["exports"]["p95_ms"], 2),
        "export_p99_ms": round(r["exports"]["p99_ms"], 2),
        "query_p95_ms": round(r["queries"]["p95_ms"], 2),
        "query_p99_ms": round(r["queries"]["p99_ms"], 2),
        # "Through ingestion" is the window from the start of the query workers
        # to the end of offered ingestion. It has the same length for every
        # backend; the full-run figures above also cover index catch-up.
        "completed_queries_through_ingestion": sum(phase["queries"]["result_codes"].values()),
        "query_p95_through_ingestion_ms": round(phase["queries"]["p95_ms"], 2),
        "query_p99_through_ingestion_ms": round(phase["queries"]["p99_ms"], 2),
        "workload_seconds": round(r["exports"]["workload_seconds"], 2),
        "completed_work_seconds": round(r["completed_work_seconds"], 2),
        "catchup_seconds": round(r["indexing"].get("catchup_seconds") or 0, 2),
        "export_retries": {k: v for k, v in r["exports"]["attempt_codes"].items() if k != "OK"},
    }
    for service in ("backend", "ingestion"):
        out[f"{service}_cpu_s_ingestion"] = round(
            phase["containers"][service]["cpu_usage_seconds"] - before[service]["cpu_usage_seconds"], 2)
        out[f"{service}_cpu_s_completed"] = round(
            after[service]["cpu_usage_seconds"] - before[service]["cpu_usage_seconds"], 2)
        out[f"{service}_peak_sampled_mib"] = round(r["resources"][service]["max_memory_mib"], 1)
        out[f"{service}_cgroup_peak_mib"] = round(after[service]["peak_cgroup_memory_bytes"] / MIB, 1)
        if idle:
            out[f"{service}_idle_working_set_mib"] = round(idle[service]["working_set_bytes"] / MIB, 1)
            out[f"{service}_idle_cgroup_current_mib"] = round(idle[service]["memory_current_bytes"] / MIB, 1)
            out[f"{service}_idle_anon_mib"] = round(idle[service]["stat"].get("anon", 0) / MIB, 1)
            out[f"{service}_idle_process_rss_mib"] = round(idle[service]["process_rss_kib"] / 1024, 1)
        end = r["memory_after_completed_work"][service]
        out[f"{service}_end_process_rss_mib"] = round(end["process_rss_kib"] / 1024, 1)
        out[f"{service}_end_anon_mib"] = round(end["stat"].get("anon", 0) / MIB, 1)
        out[f"{service}_memory_events"] = {k: v for k, v in end["events"].items() if v}
        out[f"{service}_throttled_s"] = round(
            (after[service]["cpu_stat"].get("throttled_usec", 0) - before[service].get("cpu_stat", {}).get("throttled_usec", 0)) / 1e6, 2)
    return out


if __name__ == "__main__":
    for name in sys.argv[1:]:
        summary = summarize(Path(name))
        print(json.dumps(summary, indent=1))
