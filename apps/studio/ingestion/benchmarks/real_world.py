#!/usr/bin/env python3
"""Run the real-world test of one Studio build.

The real frontend in a browser and the real SDK use Studio while the harness's
exporters send spans to ingestion, on the supported resource profile:

    uv run python real_world.py --label candidate --output /tmp/junjo-real-world/candidate-1.json

README.md describes how to select the build, what is measured, and how to
compare two builds.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from real_world_report import describe, markdown

HERE = Path(__file__).resolve().parent
# The browser tabs stop this long before the exporters do, so every page is
# loaded while spans arrive.
ACTIVITY_ENDS_SECONDS_EARLY = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="names the build under test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--seconds", type=int, default=90, help="how long spans are offered"
    )
    parser.add_argument("--exporters", type=int, default=50)
    parser.add_argument("--spans-per-export", type=int, default=32)
    parser.add_argument(
        "--export-interval-ms",
        type=int,
        default=100,
        help="each exporter sends one trace this often",
    )
    parser.add_argument("--tabs", type=int, default=4, help="browser tabs")
    parser.add_argument(
        "--history-pages",
        action="store_true",
        help="also load the Agents page and an execution link, which read a "
        "service's whole history",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend-port", type=int, default=27154)
    parser.add_argument("--ingestion-port", type=int, default=27155)
    args = parser.parse_args()

    activity = [sys.executable, str(HERE / "real_world_activity.py")]
    command = [
        sys.executable,
        str(HERE / "auth_path_benchmark.py"),
        "--implementation-label",
        args.label,
        "--exporters",
        str(args.exporters),
        "--exports-per-exporter",
        str(args.seconds * 1000 // args.export_interval_ms),
        "--spans-per-export",
        str(args.spans_per_export),
        "--export-interval-ms",
        str(args.export_interval_ms),
        "--span-shape",
        "studio",
        # The browser and the SDK are the queries of this run.
        "--query-workers",
        "0",
        "--freshness-probe",
        "--side-command",
        shlex.join(activity),
        "--skip-revocation",
        "--wal-probe-spans",
        "0",
        "--backend-port",
        str(args.backend_port),
        "--ingestion-port",
        str(args.ingestion_port),
        "--output",
        str(args.output),
    ]
    if args.skip_build:
        command.append("--skip-build")
    environment = {
        **os.environ,
        "JUNJO_REAL_WORLD_SECONDS": str(args.seconds - ACTIVITY_ENDS_SECONDS_EARLY),
        "JUNJO_REAL_WORLD_TABS": str(args.tabs),
        "JUNJO_REAL_WORLD_HISTORY_PAGES": "1" if args.history_pages else "0",
    }
    # The harness prints its whole result, which is read from the output file
    # instead. What it writes to its error stream is kept beside the result.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    harness_log = args.output.with_suffix(".harness.log")
    with harness_log.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command, cwd=HERE, env=environment, stdout=subprocess.DEVNULL, stderr=log
        )
    if not args.output.is_file():
        print(f"The harness wrote no result. See {harness_log}", file=sys.stderr)
        return completed.returncode or 1
    result = json.loads(args.output.read_text(encoding="utf-8"))
    print(markdown([(args.label, [describe(result)])]))
    failed = [name for name, passed in result["acceptance"].items() if not passed]
    if failed:
        print(f"\nFailed harness checks: {', '.join(failed)}", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
