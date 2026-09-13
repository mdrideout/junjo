#!/usr/bin/env python3
"""Run the bounded low-resource authorization candidate matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCHMARK = Path(__file__).with_name("auth_path_benchmark.py")


@dataclass(frozen=True)
class Scenario:
    name: str
    arguments: tuple[str, ...]
    expect_success: bool = True
    expected_final_code: str | None = None


def arguments(**values: int | str) -> tuple[str, ...]:
    rendered: list[str] = []
    for name, value in values.items():
        rendered.extend((f"--{name.replace('_', '-')}", str(value)))
    return tuple(rendered)


def scenarios() -> list[Scenario]:
    matrix: list[Scenario] = []

    for ttl in (5, 10, 15, 30):
        matrix.append(
            Scenario(
                f"ttl-{ttl}",
                arguments(
                    cache_ttl_seconds=ttl,
                    exporters=10,
                    exports_per_exporter=120,
                    spans_per_export=32,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="shared",
                    timing="synchronized",
                ),
            )
        )

    for capacity in (256, 1024):
        matrix.append(
            Scenario(
                f"capacity-{capacity}",
                arguments(
                    cache_max_entries=capacity,
                    exporters=300,
                    exports_per_exporter=2,
                    spans_per_export=1,
                    query_workers=0,
                    export_interval_ms=100,
                    key_topology="distinct",
                    timing="synchronized",
                )
                + ("--round-barrier",),
            )
        )

    for concurrency in (4, 8, 16):
        matrix.append(
            Scenario(
                f"concurrency-{concurrency}",
                arguments(
                    validation_max_concurrency=concurrency,
                    exporters=100,
                    exports_per_exporter=10,
                    spans_per_export=32,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="distinct",
                    timing="synchronized",
                ),
            )
        )

    for repeat in (2, 3):
        for concurrency in (4, 8, 16):
            matrix.append(
                Scenario(
                    f"concurrency-{concurrency}-repeat-{repeat}",
                    arguments(
                        validation_max_concurrency=concurrency,
                        exporters=100,
                        exports_per_exporter=10,
                        spans_per_export=32,
                        query_workers=2,
                        export_interval_ms=100,
                        key_topology="distinct",
                        timing="synchronized",
                    ),
                )
            )

    for pending in (16, 32, 64):
        matrix.append(
            Scenario(
                f"pending-{pending}",
                arguments(
                    validation_max_pending=pending,
                    exporters=100,
                    exports_per_exporter=10,
                    spans_per_export=32,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="distinct",
                    timing="synchronized",
                ),
            )
        )

    for repeat in (2, 3):
        for pending in (16, 32, 64):
            matrix.append(
                Scenario(
                    f"pending-{pending}-repeat-{repeat}",
                    arguments(
                        validation_max_pending=pending,
                        exporters=100,
                        exports_per_exporter=10,
                        spans_per_export=32,
                        query_workers=2,
                        export_interval_ms=100,
                        key_topology="distinct",
                        timing="synchronized",
                    ),
                )
            )

    for deadline in (1000, 2000, 5000):
        expected_success = deadline > 1250
        matrix.append(
            Scenario(
                f"deadline-{deadline}-delay-1250",
                arguments(
                    validation_timeout_ms=deadline,
                    workload_auth_delay_ms=1250,
                    exporters=10,
                    exports_per_exporter=3,
                    spans_per_export=1,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="shared",
                    timing="synchronized",
                    max_retries=0,
                ),
                expect_success=expected_success,
                expected_final_code=None if expected_success else "UNAVAILABLE",
            )
        )

    for span_count in (1, 32, 128, 512):
        matrix.append(
            Scenario(
                f"spans-{span_count}",
                arguments(
                    exporters=20,
                    exports_per_exporter=20,
                    spans_per_export=span_count,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="shared",
                    timing="staggered",
                ),
            )
        )

    for exporter_count, exports_per_exporter in ((1, 100), (10, 100), (100, 30)):
        matrix.append(
            Scenario(
                f"exporters-{exporter_count}",
                arguments(
                    exporters=exporter_count,
                    exports_per_exporter=exports_per_exporter,
                    spans_per_export=32,
                    query_workers=2,
                    export_interval_ms=100,
                    key_topology="shared",
                    timing="staggered",
                ),
            )
        )

    for topology in ("shared", "distinct"):
        for timing in ("synchronized", "staggered"):
            matrix.append(
                Scenario(
                    f"topology-{topology}-{timing}",
                    arguments(
                        exporters=100,
                        exports_per_exporter=10,
                        spans_per_export=32,
                        query_workers=2,
                        export_interval_ms=100,
                        key_topology=topology,
                        timing=timing,
                    ),
                )
            )

    for ttl in (5, 10):
        matrix.append(
            Scenario(
                f"cadence-after-completion-5s-ttl-{ttl}-distinct",
                arguments(
                    cache_ttl_seconds=ttl,
                    exporters=100,
                    exports_per_exporter=4,
                    spans_per_export=32,
                    query_workers=2,
                    export_interval_ms=5000,
                    cadence_mode="after-completion",
                    key_topology="distinct",
                    timing="staggered",
                ),
            )
        )

    return matrix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port-base", type=int, default=29000)
    parser.add_argument("--scenario", action="append", dest="selected_scenarios")
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="replace selected scenarios in an existing output document",
    )
    return parser.parse_args()


def scenario_matches_expectation(
    scenario: Scenario, returncode: int, result: dict[str, Any]
) -> bool:
    acceptance = result.get("acceptance", {})
    all_accepted = bool(acceptance) and all(acceptance.values())
    if scenario.expect_success:
        return returncode == 0 and all_accepted
    if returncode == 0 or all_accepted:
        return False
    if scenario.expected_final_code is None:
        return True
    final_codes = result.get("exports", {}).get("final_codes", {})
    return int(final_codes.get(scenario.expected_final_code, 0)) > 0


def main() -> int:
    args = parse_args()
    selected = scenarios()
    if args.selected_scenarios:
        names = set(args.selected_scenarios)
        selected = [scenario for scenario in selected if scenario.name in names]
        missing = names - {scenario.name for scenario in selected}
        if missing:
            raise ValueError(f"unknown scenarios: {sorted(missing)}")

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="junjo-auth-matrix-") as raw_directory:
        raw_root = Path(raw_directory)
        for index, scenario in enumerate(selected):
            backend_port = args.port_base + index * 3
            ingestion_port = backend_port + 1
            proxy_port = backend_port + 2
            raw_output = raw_root / f"{scenario.name}.json"
            command = [
                sys.executable,
                str(BENCHMARK),
                "--skip-build",
                "--skip-revocation",
                "--wal-probe-spans",
                "0",
                "--use-auth-proxy",
                "--max-retries",
                "20",
                "--implementation-label",
                f"matrix-{scenario.name}",
                "--backend-port",
                str(backend_port),
                "--ingestion-port",
                str(ingestion_port),
                "--proxy-port",
                str(proxy_port),
                "--output",
                str(raw_output),
                *scenario.arguments,
            ]
            started = time.perf_counter()
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            if raw_output.is_file():
                result = json.loads(raw_output.read_text(encoding="utf-8"))
            else:
                result = {
                    "error": "benchmark did not produce JSON",
                    "output_tail": completed.stdout[-4000:],
                }
            matched = scenario_matches_expectation(
                scenario,
                completed.returncode,
                result,
            )
            results.append(
                {
                    "name": scenario.name,
                    "expected_success": scenario.expect_success,
                    "expected_final_code": scenario.expected_final_code,
                    "returncode": completed.returncode,
                    "matched_expectation": matched,
                    "wall_seconds": time.perf_counter() - started,
                    "result": result,
                }
            )
            print(
                f"{scenario.name}: "
                f"{'PASS' if matched else 'FAIL'} "
                f"({results[-1]['wall_seconds']:.1f}s)",
                flush=True,
            )

    if args.merge_existing and args.output.is_file():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        replaced = {result["name"] for result in results}
        results = [
            result for result in existing.get("scenarios", []) if result.get("name") not in replaced
        ] + results

    document = {
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenario_count": len(results),
        "matrix_passed": all(result["matched_expectation"] for result in results),
        "scenarios": results,
    }
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if document["matrix_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
