import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from agents import Agent, RunConfig, Runner
from agents.testing import ScriptedModel, assistant_message
from agents.tracing import TracingProcessor, custom_span, get_trace_provider, trace
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from junjo.plugins.openai_agents import (
    OpenAIAgentsIntegrationError,
    instrument_openai_agents,
)
from junjo.plugins.openai_agents._trace_provider import JunjoOpenAIAgentsTraceProvider


@contextmanager
def provider_runtime() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": "junjo.tests",
                "service.name": "openai-agents-tests",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        yield provider, exporter
    finally:
        provider.shutdown()


def scripted_agent(name: str = "Coordinator") -> Agent[None]:
    return Agent(
        name=name,
        model=ScriptedModel([[assistant_message(f"{name} response")]], emit_traces=True),
    )


def span_id(span: object) -> str:
    return format(span.context.span_id, "016x")  # type: ignore[union-attr]


def trace_id(span: object) -> str:
    return format(span.context.trace_id, "032x")  # type: ignore[union-attr]


class RecordingSourceProcessor(TracingProcessor):
    def __init__(self) -> None:
        self.trace_starts: list[object] = []
        self.trace_ends: list[object] = []
        self.span_starts: list[object] = []
        self.span_ends: list[object] = []
        self.flushes = 0

    def on_trace_start(self, trace: object) -> None:
        self.trace_starts.append(trace)

    def on_trace_end(self, trace: object) -> None:
        self.trace_ends.append(trace)

    def on_span_start(self, span: object) -> None:
        self.span_starts.append(span)

    def on_span_end(self, span: object) -> None:
        self.span_ends.append(span)

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        self.flushes += 1


def test_installation_is_reference_counted_and_restores_exact_original_provider() -> None:
    original = get_trace_provider()
    with provider_runtime() as (provider, _exporter):
        first = instrument_openai_agents(tracer_provider=provider)
        installed = get_trace_provider()
        second = instrument_openai_agents(tracer_provider=provider)

        assert isinstance(installed, JunjoOpenAIAgentsTraceProvider)
        assert get_trace_provider() is installed
        first.close()
        assert get_trace_provider() is installed
        second.close()
        assert get_trace_provider() is original


def test_different_provider_is_rejected_while_integration_is_active() -> None:
    with provider_runtime() as (provider, _), provider_runtime() as (other, _):
        integration = instrument_openai_agents(tracer_provider=provider)
        try:
            with pytest.raises(OpenAIAgentsIntegrationError, match="different tracer provider"):
                instrument_openai_agents(tracer_provider=other)
        finally:
            integration.close()


@pytest.mark.asyncio
async def test_runner_hierarchy_uses_ambient_parent_and_restores_context() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        tracer = provider.get_tracer("test")
        try:
            with tracer.start_as_current_span("evaluation subject") as subject:
                await Runner.run(scripted_agent(), "Find a local place")
                assert otel_trace.get_current_span() is subject
            provider.force_flush()
        finally:
            integration.close()

    spans = exporter.get_finished_spans()
    by_type = {
        span.attributes.get("junjo.openai_agents.span.type"): span
        for span in spans
        if span.attributes.get("junjo.openai_agents.span.type") in {"task", "agent", "turn", "generation"}
    }
    workflow = next(span for span in spans if span.attributes.get("junjo.openai_agents.trace.id"))
    subject = next(span for span in spans if span.name == "evaluation subject")

    assert workflow.parent.span_id == subject.context.span_id
    assert by_type["task"].parent.span_id == workflow.context.span_id
    assert by_type["agent"].parent.span_id == by_type["task"].context.span_id
    assert by_type["turn"].parent.span_id == by_type["agent"].context.span_id
    assert by_type["generation"].parent.span_id == by_type["turn"].context.span_id


def test_explicit_trace_and_span_parents_are_preserved() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        bridge = get_trace_provider()
        try:
            source_trace = bridge.create_trace("Explicit workflow")
            source_trace.start(mark_as_current=False)
            parent = bridge.create_span(
                span_data=custom_span("unused").span_data,
                parent=source_trace,
            )
            parent.start(mark_as_current=False)
            child = bridge.create_span(
                span_data=custom_span("unused-child").span_data,
                parent=parent,
            )
            child.start(mark_as_current=False)
            child.finish()
            parent.finish()
            source_trace.finish()
            provider.force_flush()
        finally:
            integration.close()

    spans = exporter.get_finished_spans()
    workflow = next(span for span in spans if span.attributes.get("junjo.openai_agents.trace.id"))
    parent_span = next(
        span
        for span in spans
        if json.loads(span.attributes["junjo.openai_agents.span.data"])["data"]["name"] == "unused"
    )
    child_span = next(
        span
        for span in spans
        if json.loads(span.attributes["junjo.openai_agents.span.data"])["data"]["name"] == "unused-child"
    )

    assert parent_span.parent.span_id == workflow.context.span_id
    assert child_span.parent.span_id == parent_span.context.span_id


@pytest.mark.asyncio
async def test_disabled_source_tracing_emits_no_translated_spans() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        try:
            await Runner.run(
                scripted_agent(),
                "Find a local place",
                run_config=RunConfig(tracing_disabled=True),
            )
            provider.force_flush()
        finally:
            integration.close()

    assert exporter.get_finished_spans() == ()


@pytest.mark.asyncio
async def test_source_sensitive_data_policy_is_preserved() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        try:
            await Runner.run(
                scripted_agent("Private coordinator"),
                "secret input",
                run_config=RunConfig(trace_include_sensitive_data=False),
            )
            provider.force_flush()
        finally:
            integration.close()

    generation = next(
        span
        for span in exporter.get_finished_spans()
        if span.attributes.get("junjo.openai_agents.span.type") == "generation"
    )
    payload = json.loads(generation.attributes["junjo.openai_agents.span.data"])

    assert payload["data"]["input"] is None
    assert payload["data"]["output"] is None
    assert "secret input" not in generation.attributes["junjo.openai_agents.span.data"]


@pytest.mark.asyncio
async def test_repeated_and_concurrent_runs_have_separate_complete_traces_and_no_retained_maps() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        bridge = get_trace_provider()
        assert isinstance(bridge, JunjoOpenAIAgentsTraceProvider)
        try:
            await Runner.run(scripted_agent("Sequential one"), "one")
            await Runner.run(scripted_agent("Sequential two"), "two")
            await asyncio.gather(
                Runner.run(scripted_agent("Concurrent one"), "three"),
                Runner.run(scripted_agent("Concurrent two"), "four"),
            )
            provider.force_flush()
            assert bridge._active_traces == {}
            assert bridge._active_spans == {}
        finally:
            integration.close()

    translated = [
        span
        for span in exporter.get_finished_spans()
        if span.attributes.get("junjo.openai_agents.schema_version") == 1
    ]
    trace_ids = {trace_id(span) for span in translated}
    workflow_spans = [span for span in translated if span.attributes.get("junjo.openai_agents.trace.id")]

    assert len(trace_ids) == 4
    assert len(workflow_spans) == 4
    for current_trace_id in trace_ids:
        trace_spans = [span for span in translated if trace_id(span) == current_trace_id]
        ids = {span_id(span) for span in trace_spans}
        assert all(span.parent is None or format(span.parent.span_id, "016x") in ids for span in trace_spans)


def test_source_error_and_cancellation_end_spans_without_changing_control_flow() -> None:
    with provider_runtime() as (provider, exporter):
        integration = instrument_openai_agents(tracer_provider=provider)
        try:
            with trace("Failure workflow"):
                with custom_span("failing operation") as failing:
                    failing.set_error(
                        {"message": "Operation failed", "data": {"name": "ApplicationError"}}
                    )
                with pytest.raises(asyncio.CancelledError):
                    with custom_span("cancelled operation"):
                        raise asyncio.CancelledError()
            provider.force_flush()
        finally:
            integration.close()

    by_name = {span.name: span for span in exporter.get_finished_spans()}
    failed = by_name["custom failing operation"]
    cancelled = by_name["custom cancelled operation"]

    assert failed.status.status_code.name == "ERROR"
    assert failed.attributes["error.type"] == "ApplicationError"
    assert cancelled.status.status_code.name == "ERROR"
    assert any(event.name == "exception" for event in cancelled.events)


def test_provider_delegates_source_processors_and_identifiers() -> None:
    original = get_trace_provider()
    with provider_runtime() as (provider, _):
        integration = instrument_openai_agents(tracer_provider=provider)
        bridge = get_trace_provider()
        try:
            assert isinstance(bridge, JunjoOpenAIAgentsTraceProvider)
            assert bridge.time_iso()
            assert bridge.gen_trace_id().startswith("trace_")
            assert bridge.gen_span_id().startswith("span_")
            assert bridge.gen_group_id().startswith("group_")
            bridge.set_disabled(False)
            bridge.force_flush()
            assert bridge.get_current_trace() is original.get_current_trace()
            assert bridge.get_current_span() is original.get_current_span()
        finally:
            integration.close()


def test_original_source_processors_receive_the_unchanged_source_lifecycle() -> None:
    original = get_trace_provider()
    recorder = RecordingSourceProcessor()
    original.set_processors([recorder])
    try:
        with provider_runtime() as (provider, _):
            integration = instrument_openai_agents(tracer_provider=provider)
            try:
                with trace("Preserved source workflow"):
                    with custom_span("preserved source span"):
                        pass
                get_trace_provider().force_flush()
            finally:
                integration.close()
    finally:
        original.set_processors([])

    assert len(recorder.trace_starts) == 1
    assert recorder.trace_starts == recorder.trace_ends
    assert len(recorder.span_starts) == 1
    assert recorder.span_starts == recorder.span_ends
    assert recorder.flushes == 1


def test_close_is_idempotent() -> None:
    original = get_trace_provider()
    with provider_runtime() as (provider, _):
        integration = instrument_openai_agents(tracer_provider=provider)
        integration.close()
        integration.close()
    assert get_trace_provider() is original
