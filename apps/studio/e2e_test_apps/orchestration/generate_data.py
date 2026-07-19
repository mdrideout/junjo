"""CLI tool for generating test data with configurable concurrency."""

import argparse
import asyncio
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coolname import generate_slug

# Configure OTEL BatchSpanProcessor for high throughput
# These are inherited by subprocesses
os.environ.setdefault("OTEL_BSP_SCHEDULE_DELAY", "100")  # 100ms instead of 5000ms
os.environ.setdefault("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "2048")  # 2048 instead of 512
os.environ.setdefault("OTEL_BSP_MAX_QUEUE_SIZE", "8192")  # 8192 instead of 2048


def positive_int(value: str) -> int:
    """Parse a strictly positive integer for a load dimension."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


@dataclass
class WorkflowRunResult:
    """Result from one subprocess execution."""

    service_name: str
    workflow_num: int
    return_code: int


async def run_workflow(
    service_name: str,
    workflow_num: int,
    config_path: str,
    workflows_per_process: int = 1,
) -> WorkflowRunResult:
    """
    Run workflows for a service.

    Args:
        service_name: Name of the service
        workflow_num: Workflow number (for tracking)
        config_path: Path to config.yaml
        workflows_per_process: Number of workflows to run per subprocess (concurrent)

    Returns:
        Workflow execution result for one subprocess.
    """
    app_dir = Path(__file__).parent.parent / "app"

    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "--frozen",
        "python",
        "main.py",
        "--config",
        config_path,
        "--service-name",
        service_name,
        "--num-workflows",
        str(workflows_per_process),
        cwd=app_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    stderr_text = stderr.decode("utf-8", errors="replace")

    if process.returncode != 0:
        print(
            f"Warning: subprocess failed for service={service_name} "
            f"cycle={workflow_num} (return code {process.returncode})"
        )
        stderr_preview = "\n".join(stderr_text.strip().splitlines()[-5:])
        if stderr_preview:
            print(stderr_preview)
    elif stderr_text.strip():
        print(f"Producer diagnostics for service={service_name} cycle={workflow_num}:")
        print("\n".join(stderr_text.strip().splitlines()[-5:]))

    return WorkflowRunResult(
        service_name=service_name,
        workflow_num=workflow_num,
        return_code=process.returncode,
    )


async def execute_round(
    services: list[str],
    round_num: int,
    config_path: str,
    workflows_per_process: int = 1,
) -> tuple[int, list[WorkflowRunResult]]:
    """
    Execute one round: all services run workflows (concurrent).

    Args:
        services: List of service names
        round_num: Round number (for tracking)
        config_path: Path to config.yaml
        workflows_per_process: Number of workflows per subprocess

    Returns:
        Tuple of (round_num, results)
    """
    tasks = [
        run_workflow(service, round_num, config_path, workflows_per_process)
        for service in services
    ]
    results = await asyncio.gather(*tasks)  # All services run together
    return round_num, results


async def generate_data(
    num_services: int,
    num_cycles: int | None,
    duration: int | None,
    concurrency: int,
    workflows_per_process: int,
    config_path: str,
):
    """
    Generate test data with controlled concurrency.

    Execution model:
        - Cycle = all services execute workflows (asyncio.gather)
        - Concurrency = number of cycles running simultaneously
        - Total concurrent workflows = num_services × concurrency × workflows_per_process

    Args:
        num_services: Number of unique services to create
        num_cycles: Number of cycles to run (ignored if duration is set)
        duration: Run for this many seconds (overrides num_cycles)
        concurrency: Number of cycles to run concurrently
        workflows_per_process: Number of workflows each subprocess runs concurrently
        config_path: Path to config.yaml for the base app
    """
    if duration is None and num_cycles is None:
        raise ValueError("num_cycles or duration is required")

    # Generate unique service names using coolname
    services = [generate_slug(3) for _ in range(num_services)]

    print(f"Generated {num_services} service names:")
    for i, name in enumerate(services, 1):
        print(f"  {i}. {name}")
    print()

    total_concurrent = num_services * concurrency * workflows_per_process
    print("Configuration:")
    print(f"  Services: {num_services}")
    if duration is not None:
        print(f"  Duration: {duration} seconds")
    else:
        print(f"  Cycles: {num_cycles}")
    print(f"  Concurrency: {concurrency} cycles")
    print(f"  Workflows per process: {workflows_per_process}")
    print(f"  Total concurrent workflows: {total_concurrent}")
    print()

    start = time.time()
    cycle_num = 0
    cycles_completed = 0
    failed_processes = 0

    # Duration-based mode
    if duration is not None:
        end_time = start + duration
        print(f"Running for {duration} seconds...")

        while time.time() < end_time:
            # Create batch of cycles
            batch = []
            for _ in range(concurrency):
                if time.time() >= end_time:
                    break
                batch.append(
                    execute_round(
                        services, cycle_num, config_path, workflows_per_process
                    )
                )
                cycle_num += 1

            if batch:
                batch_results = await asyncio.gather(*batch)
                cycles_completed += len(batch)
                for _, results in batch_results:
                    for result in results:
                        if result.return_code != 0:
                            failed_processes += 1
                elapsed = time.time() - start
                workflows_so_far = (
                    cycles_completed * num_services * workflows_per_process
                )
                print(
                    f"Progress: {cycles_completed} cycles, {workflows_so_far} workflows "
                    f"({elapsed:.1f}s elapsed)"
                )

    # Cycle-based mode
    else:
        assert num_cycles is not None
        rounds = []
        for round_num in range(num_cycles):
            rounds.append(
                execute_round(services, round_num, config_path, workflows_per_process)
            )

        # Execute rounds with concurrency limit
        for i in range(0, len(rounds), concurrency):
            batch = rounds[i : i + concurrency]
            batch_results = await asyncio.gather(*batch)
            cycles_completed += len(batch)
            for _, results in batch_results:
                for result in results:
                    if result.return_code != 0:
                        failed_processes += 1

            workflows_so_far = cycles_completed * num_services * workflows_per_process
            print(
                f"Progress: {cycles_completed}/{num_cycles} cycles, "
                f"{workflows_so_far} workflows"
            )

    elapsed = time.time() - start
    total_workflows = num_services * cycles_completed * workflows_per_process
    throughput_workflows_per_sec = total_workflows / elapsed if elapsed > 0 else 0

    # Save metadata for verification
    metadata = {
        "config": {
            "num_services": num_services,
            "num_cycles": cycles_completed,
            "duration_seconds": duration,
            "concurrency": concurrency,
            "workflows_per_process": workflows_per_process,
        },
        "services": services,
        "results": {
            "total_workflows": total_workflows,
            "cycles_completed": cycles_completed,
            "workflows_per_service": cycles_completed * workflows_per_process,
            "duration_seconds": round(elapsed, 2),
            "throughput_workflows_per_sec": round(throughput_workflows_per_sec, 2),
            "failed_processes": failed_processes,
        },
    }

    output_path = Path(__file__).parent / "test_run_metadata.json"
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)

    failed = failed_processes > 0

    print()
    status = "❌ Failed" if failed else "✅ Completed"
    print(f"{status}: {total_workflows} workflows in {elapsed:.2f}s")
    print(f"   Cycles completed: {cycles_completed}")
    print(f"   Workflows per service: {cycles_completed * workflows_per_process}")
    print(f"   Throughput: {throughput_workflows_per_sec:.2f} workflows/sec")
    if failed_processes:
        print(f"   Warning: {failed_processes} subprocesses failed")
    print(f"   Metadata saved to: {output_path}")

    return metadata


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate test data for Junjo AI Studio E2E testing"
    )
    parser.add_argument(
        "--num-services",
        type=positive_int,
        required=True,
        help="Number of unique services to create",
    )
    parser.add_argument(
        "--num-cycles",
        type=positive_int,
        help="Number of cycles to run (each cycle = all services run 1 workflow)",
    )
    parser.add_argument(
        "--duration",
        type=positive_int,
        help="Run for this many seconds (overrides --num-cycles)",
    )
    parser.add_argument(
        "--concurrency",
        type=positive_int,
        default=5,
        help="Number of cycles to run concurrently (default: 5)",
    )
    parser.add_argument(
        "--workflows-per-process",
        type=positive_int,
        default=1,
        help="Number of workflows each subprocess runs concurrently (default: 1)",
    )
    parser.add_argument(
        "--config",
        default="../app/config.yaml",
        help="Path to config file (default: ../app/config.yaml)",
    )
    args = parser.parse_args(argv)

    # Validation
    if args.duration is None and args.num_cycles is None:
        parser.error("Must specify either --num-cycles or --duration")

    return args


def generation_failed(metadata: dict[str, Any]) -> bool:
    """Return whether any producer subprocess failed."""
    return metadata["results"]["failed_processes"] > 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run data generation and fail closed when any producer is incomplete."""
    args = parse_args(argv)

    metadata = asyncio.run(
        generate_data(
            args.num_services,
            args.num_cycles,
            args.duration,
            args.concurrency,
            args.workflows_per_process,
            args.config,
        )
    )
    return 1 if generation_failed(metadata) else 0


if __name__ == "__main__":
    raise SystemExit(main())
