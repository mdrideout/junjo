"""Drive one or more evidence runs. Usage: run.py <label-prefix> <variant>:<shape>:<rep> ..."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path("/Users/matt/repos/junjo/apps/studio")
OBSERVER_IMAGE = "junjo-rsmig-python-backend:0.85.0"

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
    # Index completion, then filtered queries over the 16 indexed cold files.
    "filtered": ["--exports-per-exporter", "800", "--query-workers", "0", "--export-interval-ms", "0",
                 "--trace-queries", "200", "--list-queries", "60"],
    # The mixed cadence, with the query workers asking for traces or for a
    # service's newest root spans while spans arrive.
    "live-trace": ["--exports-per-exporter", "300", "--query-workers", "8", "--export-interval-ms", "100",
                   "--workload-query", "trace"],
    "live-list": ["--exports-per-exporter", "300", "--query-workers", "4", "--export-interval-ms", "100",
                  "--workload-query", "list"],
    # Real-world runs: the mixed cadence for 90 seconds with no API-level query
    # workers. The real frontend in a browser (four tabs) and the real SDK query
    # while spans arrive, and a probe times how long a new trace takes to
    # become readable.
    "realworld": ["--exports-per-exporter", "900", "--query-workers", "0", "--export-interval-ms", "100",
                  "--freshness-probe",
                  "--side-command", "RW_DURATION_SECONDS=85 RW_TABS=4 python3 /private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/realworld/side.py"],
    # The same with four times the span rate: one export per exporter every 25 ms.
    "realworld-heavy": ["--exports-per-exporter", "3600", "--query-workers", "0", "--export-interval-ms", "25",
                        "--freshness-probe",
                        "--side-command", "RW_DURATION_SECONDS=85 RW_TABS=4 python3 /private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/realworld/side.py"],
    # A short run to check the plumbing. Not a measurement.
    "realworld-dry": ["--exports-per-exporter", "450", "--query-workers", "0", "--export-interval-ms", "100",
                      "--freshness-probe",
                      "--side-command", "RW_DURATION_SECONDS=40 RW_TABS=2 python3 /private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/realworld/side.py"],
    # The filtered shape with 32 spans exported after indexing completes and
    # left unflushed, so every query also reads a hot snapshot.
    "filtered-hot": ["--exports-per-exporter", "800", "--query-workers", "0", "--export-interval-ms", "0",
                     "--trace-queries", "200", "--list-queries", "20", "--hot-spans", "32"],
}
# The harness defaults to the Rust backend's setup routes.
PYTHON_PATHS = ["--first-user-path", "/users/create-first-user", "--api-keys-path", "/api_keys"]


def variant_settings(variant: str) -> tuple[str, list[str]]:
    if variant.startswith("python"):
        return f"overlay-{variant}.yaml", PYTHON_PATHS
    if variant.startswith("rust") or variant.startswith("proto"):
        return f"overlay-{variant}.yaml", []
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
        "uv", "run", "--project", str(ROOT / "benchmarks"), "python", str(ROOT / "benchmarks/auth_path_benchmark.py"),
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
