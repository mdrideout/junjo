"""Compare repeated baseline/candidate runs without hiding failed delivery.

Threshold arguments are explicit review inputs, not new product defaults.
"""

import argparse
import json
import statistics
from pathlib import Path


def metrics(result: dict) -> dict[str, float]:
    values = {
        "spans_per_second": result["exports"]["spans_per_second"],
        "export_p95_ms": result["exports"]["p95_ms"],
        "export_p99_ms": result["exports"]["p99_ms"],
        "query_p95_ms": result["queries"]["p95_ms"],
    }
    for service in ("backend", "ingestion"):
        before = result["container_before"][service]
        after = result["container_after"][service]
        values[f"{service}_cpu_us_per_span"] = (
            (after["cpu_usage_seconds"] - before["cpu_usage_seconds"])
            * 1_000_000
            / result["exports"]["acknowledged_spans"]
        )
        values[f"{service}_peak_memory_mib"] = result["resources"][service][
            "max_memory_mib"
        ]
        values[f"{service}_cgroup_peak_mib"] = (
            after["peak_cgroup_memory_bytes"] / 1024**2
        )
    return values


def compare(baseline: list[dict], candidate: list[dict]) -> dict:
    runs = baseline + candidate
    reference = {
        key: value
        for key, value in runs[0]["config"].items()
        if key != "implementation_label"
    }
    for run in runs:
        if not run["acceptance"] or not all(run["acceptance"].values()):
            raise ValueError(
                "cannot accept a performance comparison with failed benchmark checks"
            )
        config = {
            key: value
            for key, value in run["config"].items()
            if key != "implementation_label"
        }
        if config != reference or run["constraints"] != runs[0]["constraints"]:
            raise ValueError(
                "baseline and candidate must use identical workloads and resource limits"
            )
        if not run["config"].get("verify_delivery") or not run.get("delivery", {}).get(
            "all_acknowledged_spans_persisted"
        ):
            raise ValueError("verified delivery is required for performance acceptance")
        for service in ("backend", "ingestion"):
            if run["container_after"][service].get("cpuset_cpus", "") != runs[0][
                "container_after"
            ][service].get("cpuset_cpus", ""):
                raise ValueError("actual container CPU affinity differs")
            for field in ("nano_cpus", "memory_limit_bytes", "memory_swap_bytes"):
                if (
                    run["container_after"][service][field]
                    != runs[0]["container_after"][service][field]
                ):
                    raise ValueError("actual container limits differ")
    measured = [[metrics(run) for run in group] for group in (baseline, candidate)]
    comparison = {}
    for key in measured[0][0]:
        old = [run[key] for run in measured[0]]
        new = [run[key] for run in measured[1]]
        old_median, new_median = statistics.median(old), statistics.median(new)
        comparison[key] = {
            "baseline_median": old_median,
            "candidate_median": new_median,
            "baseline_range": [min(old), max(old)],
            "candidate_range": [min(new), max(new)],
            "change_percent": (new_median / old_median - 1) * 100
            if old_median
            else None,
        }
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, nargs="+", required=True)
    parser.add_argument("--candidate", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--max-throughput-regression-percent", type=float, required=True
    )
    parser.add_argument("--max-query-p95-regression-percent", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparison = compare(
        [json.loads(path.read_text()) for path in args.baseline],
        [json.loads(path.read_text()) for path in args.candidate],
    )
    throughput_change = comparison["spans_per_second"]["change_percent"]
    query_change = comparison["query_p95_ms"]["change_percent"]
    passed = throughput_change >= -args.max_throughput_regression_percent and (
        query_change is None or query_change <= args.max_query_p95_regression_percent
    )
    result = {
        "passed": passed,
        "metrics": comparison,
        "baseline_files": [str(path) for path in args.baseline],
        "candidate_files": [str(path) for path in args.candidate],
        "limits": {
            "throughput_regression_percent": args.max_throughput_regression_percent,
            "query_p95_regression_percent": args.max_query_p95_regression_percent,
        },
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
