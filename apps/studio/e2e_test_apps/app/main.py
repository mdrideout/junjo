"""Simple Junjo app based on getting_started example."""

import argparse
import asyncio
from builtins import BaseExceptionGroup
from collections.abc import Sequence
from typing import Any

import yaml
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from workflows import create_workflow

LOCAL_DRAIN_BUDGET_MILLIS = 120_000


def positive_int(value: str) -> int:
    """Parse a strictly positive integer for a load dimension."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def load_config(config_path: str) -> dict:
    """Load YAML configuration file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


# Predefined item lists for variation
ITEM_LISTS = [
    ["laser", "coffee", "horse"],
    ["python", "gopher", "rust", "typescript"],
    ["apple", "banana"],
    ["alpha", "beta", "gamma", "delta", "epsilon"],
    ["red", "green", "blue", "yellow"],
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E Test Application for Junjo AI Studio"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--service-name",
        help="Override service name from config",
    )
    parser.add_argument(
        "--num-workflows",
        type=positive_int,
        help="Override number of workflows to run",
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> None:
    """Execute workflows and deliver their telemetry before returning."""

    # Load configuration
    config = load_config(args.config)

    # Apply overrides
    service_name = args.service_name or config["exporter"]["service_name"]
    num_workflows = (
        args.num_workflows
        if args.num_workflows is not None
        else config["app"]["num_workflows"]
    )
    if (
        not isinstance(num_workflows, int)
        or isinstance(num_workflows, bool)
        or num_workflows <= 0
    ):
        raise ValueError("app.num_workflows must be a positive integer")

    # Studio's ingestion boundary is standard OTLP traces. Configure it
    # directly so this released-SDK compatibility harness is independent of
    # convenience-exporter API changes.
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{config['exporter']['host']}:{config['exporter']['port']}",
        insecure=config["exporter"]["insecure"],
        headers=(("x-junjo-api-key", config["exporter"]["api_key"]),),
        timeout=120,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    execution_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []

    try:
        print(f"[{service_name}] Starting {num_workflows} workflow(s) concurrently...")

        workflows = [
            create_workflow(ITEM_LISTS[index % len(ITEM_LISTS)])
            for index in range(num_workflows)
        ]

        async def run_workflow(index: int, workflow: Any) -> tuple[int, str]:
            result = await workflow.execute()
            return index, result.state.model_dump_json()

        workflow_tasks: list[asyncio.Task[tuple[int, str]]] = []
        async with asyncio.TaskGroup() as task_group:
            workflow_tasks = [
                task_group.create_task(run_workflow(index, workflow))
                for index, workflow in enumerate(workflows)
            ]
        results = [task.result() for task in workflow_tasks]

        for index, final_state in results:
            print(
                f"[{service_name}] Workflow {index + 1}/{num_workflows} completed. "
                f"Final state: {final_state}"
            )

        print(f"[{service_name}] Completed {num_workflows} workflow(s)")
    except BaseException as error:
        execution_error = error

    print(f"[{service_name}] Draining the local telemetry queue...")
    drain_completed = False
    try:
        drain_completed = provider.force_flush(
            timeout_millis=LOCAL_DRAIN_BUDGET_MILLIS
        )
        if not drain_completed:
            cleanup_errors.append(
                RuntimeError("Local telemetry queue drain did not complete")
            )
    except BaseException as error:
        cleanup_errors.append(error)
    finally:
        try:
            provider.shutdown()
        except BaseException as error:
            cleanup_errors.append(error)

    if execution_error is not None:
        cleanup_errors.insert(0, execution_error)

    if len(cleanup_errors) == 1:
        raise cleanup_errors[0]
    if cleanup_errors:
        raise BaseExceptionGroup(
            "Workflow execution or telemetry cleanup failed", cleanup_errors
        )

    if drain_completed:
        print(f"[{service_name}] Local telemetry queue drained")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    asyncio.run(run(parse_args(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
