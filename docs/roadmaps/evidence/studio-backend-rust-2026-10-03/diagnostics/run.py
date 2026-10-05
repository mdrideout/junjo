"""Drive one or more evidence runs. Usage: run.py <label-prefix> <variant>:<shape>:<rep> ..."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path("/Users/matt/repos/junjo/apps/studio")
OBSERVER_IMAGE = "junjo-rsmig-python-backend:local"

SHAPES = {
    # The September 2026 accepted shapes.
    "mixed": ["--exports-per-exporter", "300", "--query-workers", "2", "--export-interval-ms", "100"],
    "saturation": ["--exports-per-exporter", "800", "--query-workers", "0", "--export-interval-ms", "0"],
    "long-mixed": ["--exports-per-exporter", "600", "--query-workers", "2", "--export-interval-ms", "100"],
    # The mixed cadence with no query workers: isolates the effect of queries.
    "paced": ["--exports-per-exporter", "300", "--query-workers", "0", "--export-interval-ms", "100"],
    # Mixed load with one key per exporter, routed through the counting proxy,
    # so ValidateApiKey latency is recorded while queries run.
    "mixed-proxy": ["--exports-per-exporter", "300", "--query-workers", "2", "--export-interval-ms", "100",
                    "--use-auth-proxy", "--key-topology", "distinct"],
}
RUST_PATHS = ["--first-user-path", "/api/v1/users/create-first-user", "--api-keys-path", "/api/v1/api-keys"]


def variant_settings(variant: str) -> tuple[str, list[str]]:
    if variant.startswith("python"):
        return f"overlay-{variant}.yaml", []
    if variant.startswith("rust"):
        return f"overlay-{variant}.yaml", RUST_PATHS
    raise SystemExit(f"unknown variant {variant}")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


prefix = sys.argv[1]
for job in sys.argv[2:]:
    variant, shape, rep = job.split(":")
    overlay, extra = variant_settings(variant)
    label = f"{prefix}-{variant}-{shape}-{rep}"
    env = {
        **os.environ,
        "JUNJO_BENCHMARK_PROJECT_NAME": "junjo-rsmig-bench",
        "JUNJO_BENCHMARK_COMPOSE_ROOT": str(REPO),
        "JUNJO_BENCHMARK_COMPOSE_OVERLAY": str(ROOT / overlay),
    }
    command = [
        "uv", "run", "--project", "backend", "python", str(ROOT / "benchmarks/auth_path_benchmark.py"),
        "--skip-build", "--implementation-label", label,
        "--exporters", "50", "--spans-per-export", "32", *SHAPES[shape],
        "--skip-revocation", "--wal-probe-spans", "0", "--verify-delivery", "--recovery-seconds", "0",
        "--idle-seconds", os.environ.get("JUNJO_RUN_IDLE_SECONDS", "20"),
        "--observer-image", OBSERVER_IMAGE, "--index-deadline-seconds", "900",
        "--backend-port", str(free_port()), "--ingestion-port", str(free_port()), "--proxy-port", str(free_port()),
        "--output", str(ROOT / "results" / f"{label}.json"), *extra,
    ]
    print(f"START {label} {time.strftime('%H:%M:%S')}", flush=True)
    with (ROOT / "results" / f"{label}.log").open("w") as out:
        completed = subprocess.run(command, cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT)
    print(f"END {label} exit={completed.returncode} {time.strftime('%H:%M:%S')}", flush=True)
