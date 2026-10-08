"""Real-world activity beside a load run.

Started by the benchmark harness when its workload starts. For a fixed time:

- the real Studio frontend is driven in a browser, in several tabs, over the
  pages of the services the load generator writes to; and
- the real SDK runs a deterministic Agent composition, exports its spans to
  the same ingestion, and the existing validator and browser proof check that
  Studio shows it.

Environment from the harness: RW_STUDIO_URL, RW_INGESTION_PORT, RW_OUT, and
the first user's credentials. RW_DURATION_SECONDS, RW_TABS and RW_SERVICES
come from the caller.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = Path("/Users/matt/repos/junjo")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values) if values else None,
    }


def main() -> int:
    studio = os.environ["RW_STUDIO_URL"]
    ingestion_port = os.environ["RW_INGESTION_PORT"]
    out = Path(os.environ["RW_OUT"])
    duration = float(os.environ.get("RW_DURATION_SECONDS", "80"))
    tabs = os.environ.get("RW_TABS", "4")
    services = os.environ.get(
        "RW_SERVICES", "metadata-benchmark-0,metadata-benchmark-1,metadata-benchmark-2"
    )
    sdk_runs = os.environ.get("RW_SDK_RUNS", "1") == "1"
    work = Path(tempfile.mkdtemp(prefix="junjo-realworld-side-"))
    started = time.time()
    deadline = started + duration

    browser_out = work / "browser.json"
    browser = subprocess.Popen(
        [
            "node",
            str(HERE / "browser-load.mjs"),
            "--studio-url",
            studio,
            "--services",
            services,
            "--tabs",
            tabs,
            "--duration-seconds",
            str(int(duration)),
            "--out",
            str(browser_out),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # The real SDK, one run after another, while the browser loop runs.
    sdk: list[dict[str, object]] = []
    iteration = 0
    while sdk_runs and time.time() + 30 < deadline:
        iteration += 1
        evidence = work / f"agent-evidence-{iteration}.json"
        screenshot = work / f"agent-{iteration}.png"
        entry: dict[str, object] = {"iteration": iteration, "at_epoch_ms": int(time.time() * 1000)}
        begin = time.perf_counter()
        validator = subprocess.run(
            [
                "uv",
                "run",
                "--project",
                "sdks/python",
                "python",
                "tooling/scripts/validate_agent_studio_e2e.py",
                "--backend-url",
                studio,
                "--ingestion-host",
                "127.0.0.1",
                "--ingestion-port",
                ingestion_port,
                "--timeout-seconds",
                "120",
                "--evidence-output",
                str(evidence),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
        )
        entry["sdk_to_studio_seconds"] = round(time.perf_counter() - begin, 2)
        entry["sdk_to_studio_exit"] = validator.returncode
        if validator.returncode != 0:
            entry["sdk_to_studio_output"] = (validator.stdout + validator.stderr)[-600:]
            sdk.append(entry)
            continue
        begin = time.perf_counter()
        proof = subprocess.run(
            [
                "npm",
                "--prefix",
                "apps/studio/frontend",
                "run",
                "test:e2e:agent-live",
                "--",
                "--studio-url",
                studio,
                "--evidence",
                str(evidence),
                "--screenshot",
                str(screenshot),
                "--timeout-milliseconds",
                "120000",
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
        )
        entry["browser_proof_seconds"] = round(time.perf_counter() - begin, 2)
        entry["browser_proof_exit"] = proof.returncode
        if proof.returncode != 0:
            entry["browser_proof_output"] = (proof.stdout + proof.stderr)[-600:]
        sdk.append(entry)

    browser_log, _ = browser.communicate()
    result: dict[str, object] = {
        "started_epoch_ms": int(started * 1000),
        "duration_seconds": duration,
        "tabs": int(tabs),
        "browser_exit": browser.returncode,
        "browser_log": (browser_log or "")[-400:],
        "sdk_runs": sdk,
    }
    if browser_out.is_file():
        raw = json.loads(browser_out.read_text())
        families: dict[str, dict[str, object]] = {}
        for item in raw["responses"]:
            family = families.setdefault(item["family"], {"statuses": {}, "ms": []})
            statuses = family["statuses"]
            statuses[str(item["status"])] = statuses.get(str(item["status"]), 0) + 1  # type: ignore[index,union-attr]
            family["ms"].append(item["ms"])  # type: ignore[union-attr]
        result["api"] = {
            name: {"statuses": family["statuses"], **summary(family["ms"])}  # type: ignore[arg-type]
            for name, family in sorted(families.items())
        }
        actions: dict[str, dict[str, object]] = {}
        for item in raw["actions"]:
            action = actions.setdefault(item["action"], {"outcomes": {}, "ms": [], "rows": []})
            outcomes = action["outcomes"]
            outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1  # type: ignore[index,union-attr]
            action["ms"].append(item["ms"])  # type: ignore[union-attr]
            action["rows"].append(item.get("rows", 0))  # type: ignore[union-attr]
        result["pages"] = {
            name: {
                "outcomes": action["outcomes"],
                **summary(action["ms"]),  # type: ignore[arg-type]
                "rows_min": min(action["rows"]) if action["rows"] else None,  # type: ignore[type-var,arg-type]
                "rows_max": max(action["rows"]) if action["rows"] else None,  # type: ignore[type-var,arg-type]
            }
            for name, action in sorted(actions.items())
        }
        result["request_failures"] = raw["requestFailures"]
        result["page_errors"] = raw["pageErrors"][:20]
        result["server_errors"] = [item for item in raw["responses"] if item["status"] >= 500]
        result["raw_actions"] = raw["actions"]
    out.write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
