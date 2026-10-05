"""Aggregate every result into summary.json and print comparison tables.

Each result file name is <condition>-<variant>-<shape>-<rep>.json, where
condition is `wp1`/`wp2`/`diag` (host otherwise idle apart from the
maintainer's own containers) or `load` (four busy threads in a sibling
container, so the host keeps its CPUs at speed).
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize import summarize  # noqa: E402

RESULTS = Path(__file__).resolve().parent.parent / "results"
SHAPES = ("mixed-proxy", "long-mixed", "saturation", "mixed", "paced")


def parse(name: str) -> tuple[str, str, str, str]:
    condition, rest = name.split("-", 1)
    rest, rep = rest.rsplit("-", 1)
    for shape in SHAPES:
        if rest.endswith("-" + shape):
            return condition, rest[: -len(shape) - 1], shape, rep
    raise ValueError(name)


def main() -> None:
    runs = []
    for path in sorted(RESULTS.glob("*.json")):
        if path.name.endswith(".failure.json") or path.stem.startswith("smoke"):
            continue
        condition, variant, shape, rep = parse(path.stem)
        raw = json.loads(path.read_text())
        row = summarize(path)
        row.update(condition=condition, variant=variant, shape=shape, rep=rep)
        row["image_ids"] = {s: raw["container_after"][s]["image_id"] for s in ("backend", "ingestion")}
        row["recorded_at_utc"] = raw.get("recorded_at_utc")
        # The period observed before ingestion moves the indexer's 30-second
        # cycle relative to the work, so runs are only pooled when it matches.
        row["idle_seconds"] = raw["diagnostics"]["idle_seconds"]
        if raw.get("authorization_proxy", {}).get("requests"):
            proxy = raw["authorization_proxy"]
            row["validate_requests"] = proxy["requests"]
            row["validate_mean_ms"] = round(proxy["latency_micros_mean"] / 1000, 2)
            row["validate_max_ms"] = round(proxy["latency_micros_max"] / 1000, 2)
        runs.append(row)

    groups: dict[tuple[str, str, str, float], list[dict]] = {}
    for run in runs:
        key = (run["condition"], run["shape"], run["variant"], run["idle_seconds"])
        groups.setdefault(key, []).append(run)

    numeric = [
        "completed_queries", "spans_per_second", "export_p95_ms", "export_p99_ms", "query_p95_ms",
        "query_p99_ms", "completed_queries_through_ingestion", "query_p95_through_ingestion_ms",
        "query_p99_through_ingestion_ms", "completed_work_seconds", "catchup_seconds",
        "backend_cpu_s_ingestion", "backend_cpu_s_completed", "backend_throttled_s",
        "ingestion_cpu_s_ingestion", "ingestion_cpu_s_completed",
        "backend_idle_anon_mib", "backend_idle_process_rss_mib", "backend_idle_working_set_mib",
        "backend_peak_sampled_mib", "backend_cgroup_peak_mib", "backend_end_anon_mib",
        "backend_end_process_rss_mib", "ingestion_peak_sampled_mib", "ingestion_cgroup_peak_mib",
        "validate_mean_ms", "validate_max_ms",
    ]
    medians = []
    for (condition, shape, variant, idle_seconds), rows in sorted(groups.items()):
        entry = {"condition": condition, "shape": shape, "variant": variant,
                 "idle_seconds": idle_seconds, "runs": len(rows),
                 "all_accepted": all(r["accepted"] for r in rows)}
        for key in numeric:
            values = [r[key] for r in rows if r.get(key) is not None]
            if values:
                entry[key] = {"median": round(statistics.median(values), 2),
                              "min": min(values), "max": max(values)}
        medians.append(entry)

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS.parent / "summary.json"
    out.write_text(json.dumps({"runs": runs, "medians": medians}, indent=1) + "\n")

    def cell(entry: dict, key: str) -> str:
        value = entry.get(key)
        if value is None:
            return "—"
        if value["min"] == value["max"]:
            return f"{value['median']}"
        return f"{value['median']} ({value['min']}–{value['max']})"

    for condition, shape in sorted({(c, s) for c, s, _, _ in groups}):
        entries = [m for m in medians if m["condition"] == condition and m["shape"] == shape]
        print(f"\n### {condition} / {shape}")
        print("| metric | " + " | ".join(
            f"{e['variant']} idle {e['idle_seconds']:g}s (n={e['runs']})" for e in entries) + " |")
        print("|---|" + "---|" * len(entries))
        for key in numeric:
            if any(key in e for e in entries):
                print(f"| {key} | " + " | ".join(cell(e, key) for e in entries) + " |")
        print("| all accepted | " + " | ".join(str(e["all_accepted"]) for e in entries) + " |")


if __name__ == "__main__":
    main()
