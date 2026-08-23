"""Exercise the FastAPI example and report its emitted trace parentage."""

from __future__ import annotations

import asyncio
import json

import httpx
from agents import set_trace_processors
from junjo.plugins.openai_agents import instrument_openai_agents
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from base_openai_agents.telemetry import SERVICE_NAME, SERVICE_NAMESPACE, TelemetryRuntime
from base_openai_agents.web import create_app


async def _probe() -> dict[str, object]:
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
    runtime = TelemetryRuntime(
        provider=provider,
        integration=instrument_openai_agents(tracer_provider=provider),
    )
    app = create_app(telemetry_factory=lambda: runtime)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://example.test",
        ) as client:
            response = await client.post(
                "/recommendations",
                json={"message": "a realistic weekend afternoon"},
            )

    spans = exporter.get_finished_spans()
    server_span = next(span for span in spans if span.kind is SpanKind.SERVER)
    workflow_span = next(
        span
        for span in spans
        if span.attributes.get("gen_ai.operation.name") == "invoke_workflow"
    )
    return {
        "status_code": response.status_code,
        "response": response.json(),
        "server_span_name": server_span.name,
        "workflow_parent_is_server": (
            workflow_span.parent is not None
            and workflow_span.parent.span_id == server_span.context.span_id
        ),
        "workflow_shares_server_trace": (
            workflow_span.context.trace_id == server_span.context.trace_id
        ),
    }


print(json.dumps(asyncio.run(_probe()), sort_keys=True))
