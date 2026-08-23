from __future__ import annotations

import asyncio
import json

from agents import Runner
from junjo.plugins.openai_agents import instrument_openai_agents
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from base_openai_agents.application import build_openai_agent
from base_openai_agents.evals import harness
from base_openai_agents.telemetry import SERVICE_NAME, SERVICE_NAMESPACE


async def main() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": SERVICE_NAMESPACE,
                "service.name": SERVICE_NAME,
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    integration = instrument_openai_agents(
        tracer_provider=provider,
        disable_openai_trace_export=True,
    )
    try:
        result = await Runner.run(build_openai_agent(), "Find a local place.")
        provider.force_flush()
        spans = exporter.get_finished_spans()
        print(
            json.dumps(
                {
                    "output": result.final_output,
                    "operations": sorted(
                        {
                            operation
                            for span in spans
                            if isinstance(
                                operation := span.attributes.get("gen_ai.operation.name"),
                                str,
                            )
                        }
                    ),
                    "junjo_types": sorted(
                        {
                            span_type
                            for span in spans
                            if isinstance(
                                span_type := span.attributes.get("junjo.span_type"),
                                str,
                            )
                        }
                    ),
                    "targets": sorted(descriptor.name for descriptor in harness.target_descriptors()),
                }
            )
        )
    finally:
        integration.close()
        provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
