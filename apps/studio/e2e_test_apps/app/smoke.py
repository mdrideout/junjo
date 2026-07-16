"""Locked-environment smoke for Studio's example telemetry producer."""

import asyncio

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from workflows import create_workflow


async def main() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    result = await create_workflow(["one", "two"]).execute()
    assert result.state.count is not None

    workflow_span = next(
        span
        for span in exporter.get_finished_spans()
        if span.attributes.get("junjo.span_type") == "workflow"
    )
    assert workflow_span.attributes["junjo.executable_runtime_id"] == result.run_id
    assert workflow_span.attributes["junjo.workflow.node.count"] > 0
    assert "junjo.id" not in workflow_span.attributes
    assert "junjo.parent_id" not in workflow_span.attributes


if __name__ == "__main__":
    asyncio.run(main())
