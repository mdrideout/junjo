from __future__ import annotations

import asyncio
import json

from agents import RunConfig, Runner, set_trace_processors
from junjo.plugins.openai_agents import instrument_openai_agents
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from base_openai_agents.application import OPENAI_WORKFLOW_NAME, build_openai_agent
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
    set_trace_processors([])
    integration = instrument_openai_agents(tracer_provider=provider)
    try:
        results = [
            await Runner.run(
                build_openai_agent(),
                "Find a local place.",
                run_config=RunConfig(workflow_name=OPENAI_WORKFLOW_NAME),
            ),
            await Runner.run(
                build_openai_agent(),
                "Find another local place.",
                run_config=RunConfig(workflow_name=OPENAI_WORKFLOW_NAME),
            ),
        ]
        provider.force_flush()
        spans = exporter.get_finished_spans()
        spans_by_id = {format(span.context.span_id, "016x"): span for span in spans}
        attributes_by_span = {span: span.attributes or {} for span in spans}
        translated = [span for span in spans if attributes_by_span[span].get("junjo.openai_agents.schema_version") == 1]
        native_owners = [
            span for span in spans if attributes_by_span[span].get("junjo.span_type") in {"workflow", "agent"}
        ]
        payloads = {}
        for span in translated:
            raw_payload = attributes_by_span[span].get("junjo.openai_agents.span.data")
            if isinstance(raw_payload, str):
                payloads[span] = json.loads(raw_payload)
        print(
            json.dumps(
                {
                    "outputs": [result.final_output for result in results],
                    "operations": sorted(
                        {
                            operation
                            for span in spans
                            if isinstance(
                                operation := attributes_by_span[span].get("gen_ai.operation.name"),
                                str,
                            )
                        }
                    ),
                    "junjo_types": sorted(
                        {
                            span_type
                            for span in spans
                            if isinstance(
                                span_type := attributes_by_span[span].get("junjo.span_type"),
                                str,
                            )
                        }
                    ),
                    "source_types": sorted(
                        {
                            source_type
                            for span in translated
                            if isinstance(
                                source_type := attributes_by_span[span].get("junjo.openai_agents.span.type"),
                                str,
                            )
                        }
                    ),
                    "agent_names": sorted(
                        {
                            agent_name
                            for span in translated
                            if isinstance(
                                agent_name := attributes_by_span[span].get("gen_ai.agent.name"),
                                str,
                            )
                        }
                    ),
                    "task_names": sorted(
                        {
                            payload["data"]["name"]
                            for span, payload in payloads.items()
                            if attributes_by_span[span].get("junjo.openai_agents.span.type") == "task"
                        }
                    ),
                    "fixture_model_names": sorted(
                        {
                            model_name
                            for span in spans
                            if attributes_by_span[span].get("junjo.model.fixture") is True
                            and isinstance(
                                model_name := (
                                    attributes_by_span[span].get("junjo.agent.model.name")
                                    or attributes_by_span[span].get("gen_ai.response.model")
                                    or attributes_by_span[span].get("gen_ai.request.model")
                                ),
                                str,
                            )
                        }
                    ),
                    "translated_payloads_complete": all(
                        isinstance(
                            attributes_by_span[span].get("junjo.openai_agents.span.data")
                            or attributes_by_span[span].get("junjo.openai_agents.trace.data"),
                            str,
                        )
                        for span in translated
                    ),
                    "model_payloads_complete": all(
                        payload["data"]["input"] is not None and payload["data"]["output"] is not None
                        for span, payload in payloads.items()
                        if attributes_by_span[span].get("junjo.openai_agents.span.type") == "generation"
                    ),
                    "tool_payloads_complete": all(
                        payload["data"]["input"] is not None and payload["data"]["output"] is not None
                        for span, payload in payloads.items()
                        if attributes_by_span[span].get("junjo.openai_agents.span.type") == "function"
                    ),
                    "source_trace_count": len(
                        {
                            trace_id
                            for span in translated
                            if isinstance(
                                trace_id := attributes_by_span[span].get("junjo.openai_agents.trace.id"),
                                str,
                            )
                        }
                    ),
                    "native_owners_beneath_openai_tools": all(
                        span.parent is not None
                        and attributes_by_span[spans_by_id[format(span.parent.span_id, "016x")]].get(
                            "gen_ai.operation.name"
                        )
                        == "execute_tool"
                        for span in native_owners
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
