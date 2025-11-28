"""CLI tool for generating test data with configurable concurrency."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from coolname import generate_slug


async def run_workflow(service_name: str, workflow_num: int, config_path: str) -> tuple[str, int, int]:
    """
    Run one workflow for a service.

    Args:
        service_name: Name of the service
        workflow_num: Workflow number (for tracking)
        config_path: Path to config.yaml

    Returns:
        Tuple of (service_name, workflow_num, return_code)
    """
    app_dir = Path(__file__).parent.parent / "app"

    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "python",
        "main.py",
        "--config",
        config_path,
        "--service-name",
        service_name,
        "--num-workflows",
        "1",
        cwd=app_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()
    return service_name, workflow_num, process.returncode


async def execute_round(services: list[str], round_num: int, config_path: str) -> tuple[int, list]:
    """
    Execute one round: all services run 1 workflow each (concurrent).

    Args:
        services: List of service names
        round_num: Round number (for tracking)
        config_path: Path to config.yaml

    Returns:
        Tuple of (round_num, results)
    """
    tasks = [run_workflow(service, round_num, config_path) for service in services]
    results = await asyncio.gather(*tasks)  # All services run together
    return round_num, results


async def generate_data(
    num_services: int,
    num_cycles: int | None,
    duration: int | None,
    concurrency: int,
    config_path: str,
):
    """
    Generate test data with controlled concurrency.

    Execution model:
        - Cycle = all services execute 1 workflow each (asyncio.gather)
        - Concurrency = number of cycles running simultaneously
        - Total concurrent workflows = num_services × concurrency

    Args:
        num_services: Number of unique services to create
        num_cycles: Number of cycles to run (ignored if duration is set)
        duration: Run for this many seconds (overrides num_cycles)
        concurrency: Number of cycles to run concurrently
        config_path: Path to config.yaml for the base app
    """
    # Generate unique service names using coolname
    services = [generate_slug(3) for _ in range(num_services)]

    print(f"Generated {num_services} service names:")
    for i, name in enumerate(services, 1):
        print(f"  {i}. {name}")
    print()

    total_concurrent = num_services * concurrency
    print(f"Configuration:")
    print(f"  Services: {num_services}")
    if duration:
        print(f"  Duration: {duration} seconds")
    else:
        print(f"  Cycles: {num_cycles}")
    print(f"  Concurrency: {concurrency} cycles")
    print(f"  Total concurrent workflows: {total_concurrent}")
    print()

    start = time.time()
    cycle_num = 0
    cycles_completed = 0

    # Duration-based mode
    if duration:
        end_time = start + duration
        print(f"Running for {duration} seconds...")

        while time.time() < end_time:
            # Create batch of cycles
            batch = []
            for _ in range(concurrency):
                if time.time() >= end_time:
                    break
                batch.append(execute_round(services, cycle_num, config_path))
                cycle_num += 1

            if batch:
                await asyncio.gather(*batch)
                cycles_completed += len(batch)
                elapsed = time.time() - start
                print(f"Progress: {cycles_completed} cycles completed ({elapsed:.1f}s elapsed)")

    # Cycle-based mode
    else:
        rounds = []
        for round_num in range(num_cycles):
            rounds.append(execute_round(services, round_num, config_path))

        # Execute rounds with concurrency limit
        for i in range(0, len(rounds), concurrency):
            batch = rounds[i : i + concurrency]
            await asyncio.gather(*batch)
            cycles_completed += len(batch)
            print(f"Progress: {cycles_completed}/{num_cycles} cycles completed")

    elapsed = time.time() - start
    total = num_services * cycles_completed

    # Save metadata for verification
    metadata = {
        "config": {
            "num_services": num_services,
            "num_cycles": cycles_completed,
            "duration_seconds": duration,
            "concurrency": concurrency,
        },
        "services": services,
        "results": {
            "total_workflows": total,
            "cycles_completed": cycles_completed,
            "workflows_per_service": cycles_completed,
            "duration_seconds": round(elapsed, 2),
            "throughput": round(total / elapsed, 2),
        },
    }

    output_path = Path(__file__).parent / "test_run_metadata.json"
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print()
    print(f"✅ Completed: {total} workflows in {elapsed:.2f}s")
    print(f"   Cycles completed: {cycles_completed}")
    print(f"   Workflows per service: {cycles_completed}")
    print(f"   Throughput: {total / elapsed:.2f} workflows/sec")
    print(f"   Metadata saved to: {output_path}")

    return metadata


def main():
    parser = argparse.ArgumentParser(
        description="Generate test data for Junjo AI Studio E2E testing"
    )
    parser.add_argument(
        "--num-services",
        type=int,
        required=True,
        help="Number of unique services to create",
    )
    parser.add_argument(
        "--num-cycles",
        type=int,
        help="Number of cycles to run (each cycle = all services run 1 workflow)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run for this many seconds (overrides --num-cycles)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of cycles to run concurrently (default: 5)",
    )
    parser.add_argument(
        "--config",
        default="../app/config.yaml",
        help="Path to config file (default: ../app/config.yaml)",
    )
    args = parser.parse_args()

    # Validation
    if not args.duration and not args.num_cycles:
        parser.error("Must specify either --num-cycles or --duration")

    asyncio.run(
        generate_data(
            args.num_services,
            args.num_cycles,
            args.duration,
            args.concurrency,
            args.config,
        )
    )


if __name__ == "__main__":
    main()
