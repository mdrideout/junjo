"""Simple Junjo app based on getting_started example."""

import argparse
import asyncio

import yaml
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

from workflows import create_workflow


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


async def main():
    """The main entry point for the application."""
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
        type=int,
        help="Override number of workflows to run",
    )
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Apply overrides
    service_name = args.service_name or config["exporter"]["service_name"]
    num_workflows = args.num_workflows or config["app"]["num_workflows"]

    # Configure OpenTelemetry with Junjo exporter
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Create Junjo exporter
    exporter = JunjoServerOtelExporter(
        host=config["exporter"]["host"],
        port=config["exporter"]["port"],
        api_key=config["exporter"]["api_key"],
        insecure=config["exporter"]["insecure"],
    )

    # Add span processor and set as global tracer provider
    provider.add_span_processor(exporter.span_processor)
    trace.set_tracer_provider(provider)

    print(f"[{service_name}] Starting {num_workflows} workflow(s) concurrently...")

    # Create all workflows
    workflows = []
    for i in range(num_workflows):
        # Vary the items list for each workflow
        items = ITEM_LISTS[i % len(ITEM_LISTS)]
        workflows.append(create_workflow(items))

    # Run all workflows CONCURRENTLY (not sequentially)
    async def run_workflow(idx: int, workflow):
        await workflow.execute()
        final_state = await workflow.get_state_json()
        return idx, final_state

    tasks = [run_workflow(i, w) for i, w in enumerate(workflows)]
    results = await asyncio.gather(*tasks)

    for idx, final_state in results:
        print(f"[{service_name}] Workflow {idx+1}/{num_workflows} completed. Final state: {final_state}")

    print(f"[{service_name}] Completed {num_workflows} workflow(s)")

    # Flush telemetry before exit
    print(f"[{service_name}] Flushing telemetry...")
    if exporter.flush():
        print(f"[{service_name}] Telemetry flushed successfully")
    else:
        print(f"[{service_name}] Warning: Telemetry flush failed")


if __name__ == "__main__":
    asyncio.run(main())
