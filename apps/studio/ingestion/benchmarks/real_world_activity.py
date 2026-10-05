#!/usr/bin/env python3
"""What a person and an application do in Studio while spans arrive.

``real_world.py`` passes this file to the harness as its side command, and the
harness starts it together with the exporters. For a fixed time:

- the real frontend is driven in a browser, in several tabs, over the pages of
  the services the exporters write to; and
- the real SDK runs a deterministic Agent composition, exports its spans to
  the same ingestion service, and the repository's two live validators check
  that Studio's APIs and its pages show the run.

Nothing here judges what it records. The harness stores this file's output in
its result and ``real_world_report.py`` reads it.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[4]
FRONTEND = REPOSITORY / "apps/studio/frontend"
# An SDK run is started only while this much of the activity time remains.
SDK_RUN_NEEDS_SECONDS = 30
# How long the two validators wait for Studio to show a run.
VALIDATOR_TIMEOUT_SECONDS = 120


def sdk_run(studio_url: str, ingestion_port: str, work: Path, number: int) -> dict:
    """Run the SDK composition once and check that Studio shows it."""
    evidence = work / f"agent-evidence-{number}.json"
    run: dict[str, Any] = {}
    started = time.perf_counter()
    validator = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            "sdks/python",
            "python",
            "tooling/scripts/validate_agent_studio_e2e.py",
            "--backend-url",
            studio_url,
            "--ingestion-host",
            "127.0.0.1",
            "--ingestion-port",
            ingestion_port,
            "--timeout-seconds",
            str(VALIDATOR_TIMEOUT_SECONDS),
            "--evidence-output",
            str(evidence),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
    )
    run["sdk_to_studio_seconds"] = time.perf_counter() - started
    run["sdk_to_studio_exit_code"] = validator.returncode
    if validator.returncode != 0:
        run["output"] = (validator.stdout + validator.stderr)[-2000:]
        return run

    started = time.perf_counter()
    proof = subprocess.run(
        [
            "npm",
            "run",
            "test:e2e:agent-live",
            "--",
            "--studio-url",
            studio_url,
            "--evidence",
            str(evidence),
            "--screenshot",
            str(work / f"agent-{number}.png"),
            "--timeout-milliseconds",
            str(VALIDATOR_TIMEOUT_SECONDS * 1000),
        ],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    run["browser_proof_seconds"] = time.perf_counter() - started
    run["browser_proof_exit_code"] = proof.returncode
    if proof.returncode != 0:
        run["output"] = (proof.stdout + proof.stderr)[-2000:]
    return run


def main() -> int:
    studio_url = os.environ["JUNJO_BENCHMARK_STUDIO_URL"]
    ingestion_port = os.environ["JUNJO_BENCHMARK_INGESTION_PORT"]
    services = os.environ["JUNJO_BENCHMARK_SERVICES"]
    output = Path(os.environ["JUNJO_BENCHMARK_SIDE_OUTPUT"])
    seconds = int(os.environ["JUNJO_REAL_WORLD_SECONDS"])
    tabs = os.environ["JUNJO_REAL_WORLD_TABS"]
    history_pages = os.environ.get("JUNJO_REAL_WORLD_HISTORY_PAGES") == "1"

    with tempfile.TemporaryDirectory(prefix="junjo-real-world-") as directory:
        work = Path(directory)
        deadline = time.monotonic() + seconds
        browser_output = work / "browser.json"
        browser = subprocess.Popen(
            [
                "node",
                "e2e/live-load.mjs",
                "--studio-url",
                studio_url,
                "--services",
                services,
                "--tabs",
                tabs,
                "--duration-seconds",
                str(seconds),
                "--output",
                str(browser_output),
                *(["--history-pages"] if history_pages else []),
            ],
            cwd=FRONTEND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # One SDK run after another, while the browser tabs keep going.
        sdk_runs = []
        while time.monotonic() + SDK_RUN_NEEDS_SECONDS < deadline:
            sdk_runs.append(sdk_run(studio_url, ingestion_port, work, len(sdk_runs)))

        browser_log, _ = browser.communicate()
        result: dict[str, Any] = {
            "seconds": seconds,
            "sdk_runs": sdk_runs,
            "browser_exit_code": browser.returncode,
        }
        if browser.returncode == 0:
            result["browser"] = json.loads(browser_output.read_text(encoding="utf-8"))
        else:
            result["browser_log"] = browser_log[-2000:]
        output.write_text(json.dumps(result), encoding="utf-8")
    return browser.returncode


if __name__ == "__main__":
    raise SystemExit(main())
