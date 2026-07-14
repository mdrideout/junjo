"""Strict HTTP contract and explicit lifespan ownership tests."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx
import pytest
from conftest import make_harness
from junjo.agent import AgentAdmissionError, FinalOutputResponse, ToolCall, ToolCallsResponse

from ai_chat.api.app import create_app
from ai_chat.api.schemas import MessageResponse
from ai_chat.bootstrap import ChatApplication
from ai_chat.config import Settings, TelemetrySettings
from ai_chat.telemetry import TelemetryRuntime


@pytest.mark.asyncio
async def test_api_matches_the_greenfield_frontend_contract(tmp_path: Path) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "API response", "image": None})],
    )
    app = create_app(application=harness.application)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            conversations = await client.get("/api/conversations")
            assert conversations.status_code == 200
            assert conversations.json() == {"conversations": [{"id": "demo", "title": "Demo conversation"}]}

            turn = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "Hello from the API"},
            )
            assert turn.status_code == 200
            payload = turn.json()
            assert set(payload) == {
                "conversation_id",
                "workflow_run_id",
                "agent_run_id",
                "user_message",
                "assistant_message",
            }
            assert payload["conversation_id"] == "demo"
            assert payload["user_message"]["content"] == "Hello from the API"
            assert payload["assistant_message"]["content"] == "API response"
            for message in (payload["user_message"], payload["assistant_message"]):
                assert set(message) == {
                    "id",
                    "turn_id",
                    "role",
                    "content",
                    "image_url",
                    "image_alt",
                    "created_at",
                }
                assert message["image_url"] is None
                assert message["image_alt"] is None

            messages = await client.get("/api/conversations/demo/messages")
            assert messages.status_code == 200
            assert messages.json() == {
                "conversation_id": "demo",
                "messages": [payload["user_message"], payload["assistant_message"]],
            }

            rejected = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "valid", "legacy_field": True},
            )
            assert rejected.status_code == 422

            whitespace_only = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "   \n\t"},
            )
            assert whitespace_only.status_code == 422


@pytest.mark.asyncio
async def test_admitted_agent_failure_is_a_strict_server_error_envelope(
    tmp_path: Path,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="malformed-history",
                        name="search_conversation_history",
                        arguments={"limit": 0},
                    )
                ]
            )
        ],
    )
    app = create_app(application=harness.application)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "Search history"},
            )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Arguments for Tool 'search_conversation_history' failed declared validation.",
        "agent_run_id": response.json()["agent_run_id"],
        "termination_reason": "tool_input_validation_error",
    }
    assert response.json()["agent_run_id"]


@pytest.mark.asyncio
async def test_internal_agent_admission_failure_is_not_misclassified_as_http_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(tmp_path)

    async def fail_admission(*, conversation_id: str, text: str) -> None:
        assert conversation_id == "demo"
        assert text == "valid HTTP input"
        raise AgentAdmissionError(
            "Agent admission machinery failed.",
            agent_key="ai_chat",
            definition_id="definition",
            structural_id="agent_sha256:" + ("a" * 64),
            run_id="admission-run",
        )

    monkeypatch.setattr(harness.turns, "submit", fail_admission)
    app = create_app(application=harness.application)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "valid HTTP input"},
            )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Agent admission machinery failed.",
        "agent_run_id": "admission-run",
        "termination_reason": "internal_error",
    }


def test_api_image_url_and_alt_are_one_strict_pair() -> None:
    common = {
        "id": "message",
        "turn_id": "turn",
        "role": "assistant",
        "content": "image",
        "created_at": "2026-07-14T00:00:00Z",
    }
    with pytest.raises(ValueError):
        MessageResponse(**common, image_url="/api/images/one.svg", image_alt=None)
    with pytest.raises(ValueError):
        MessageResponse(**common, image_url=None, image_alt="description")
    with pytest.raises(ValueError):
        MessageResponse(**common, image_url="/api/images/one.svg", image_alt="  ")
    valid = MessageResponse(
        **common,
        image_url="/api/images/one.svg",
        image_alt="A lighthouse",
    )
    assert valid.image_alt == "A lighthouse"


class RecordingApplication(ChatApplication):
    def __init__(self, *, source: ChatApplication, events: list[str]) -> None:
        super().__init__(
            store=source.store,
            turns=source.turns,
            image_directory=source.image_directory,
        )
        self._events = events

    async def initialize(self) -> None:
        self._events.append("application-initialize")
        await super().initialize()

    async def close(self) -> None:
        self._events.append("application-close")
        await super().close()


class FakeTelemetryRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def shutdown(self) -> None:
        self._events.append("telemetry-flush-and-shutdown")


class FailingCloseApplication(RecordingApplication):
    async def close(self) -> None:
        await super().close()
        raise RuntimeError("application close failed")


class RecordingProvider:
    def __init__(
        self,
        events: list[str],
        *,
        flush_error: BaseException | None = None,
        shutdown_error: BaseException | None = None,
        name: str = "provider",
    ) -> None:
        self._events = events
        self._name = name
        self._flush_error = flush_error
        self._shutdown_error = shutdown_error

    def force_flush(self) -> None:
        self._events.append(f"{self._name}-force-flush")
        if self._flush_error is not None:
            raise self._flush_error

    def shutdown(self) -> None:
        self._events.append(f"{self._name}-shutdown")
        if self._shutdown_error is not None:
            raise self._shutdown_error


@pytest.mark.asyncio
async def test_lifespan_starts_telemetry_explicitly_and_flushes_after_application_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    harness = make_harness(tmp_path)
    application = RecordingApplication(source=harness.application, events=events)
    settings = TelemetrySettings(api_key="key", host="studio", port=26155, insecure=True)

    def fake_start(received: TelemetrySettings) -> FakeTelemetryRuntime:
        assert received is settings
        events.append("telemetry-start")
        return FakeTelemetryRuntime(events)

    monkeypatch.setattr("ai_chat.api.app.start_telemetry", fake_start)
    app = create_app(application=application, telemetry=settings)

    async with app.router.lifespan_context(app):
        assert events == ["telemetry-start", "application-initialize"]

    assert events == [
        "telemetry-start",
        "application-initialize",
        "application-close",
        "telemetry-flush-and-shutdown",
    ]


@pytest.mark.asyncio
async def test_lifespan_shuts_down_telemetry_when_application_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    harness = make_harness(tmp_path)
    application = FailingCloseApplication(source=harness.application, events=events)
    settings = TelemetrySettings(api_key="key", host="studio", port=26155, insecure=True)

    def fake_start(_: TelemetrySettings) -> FakeTelemetryRuntime:
        events.append("telemetry-start")
        return FakeTelemetryRuntime(events)

    monkeypatch.setattr("ai_chat.api.app.start_telemetry", fake_start)
    app = create_app(application=application, telemetry=settings)

    with pytest.raises(RuntimeError, match="application close failed"):
        async with app.router.lifespan_context(app):
            pass

    assert events == [
        "telemetry-start",
        "application-initialize",
        "application-close",
        "telemetry-flush-and-shutdown",
    ]


def test_telemetry_runtime_shuts_down_both_providers_when_flush_fails() -> None:
    events: list[str] = []
    trace_provider = RecordingProvider(
        events,
        name="trace",
        flush_error=RuntimeError("flush failed"),
    )
    meter_provider = RecordingProvider(events, name="meter")
    runtime = TelemetryRuntime(
        trace_provider=trace_provider,
        meter_provider=meter_provider,
    )

    with pytest.raises(RuntimeError, match="flush failed"):
        runtime.shutdown()

    assert events == [
        "trace-force-flush",
        "meter-force-flush",
        "trace-shutdown",
        "meter-shutdown",
    ]


def test_telemetry_runtime_preserves_both_cleanup_failures() -> None:
    events: list[str] = []
    trace_provider = RecordingProvider(
        events,
        name="trace",
        flush_error=RuntimeError("flush failed"),
    )
    meter_provider = RecordingProvider(
        events,
        name="meter",
        shutdown_error=RuntimeError("shutdown failed"),
    )
    runtime = TelemetryRuntime(
        trace_provider=trace_provider,
        meter_provider=meter_provider,
    )

    with pytest.raises(ExceptionGroup) as caught:
        runtime.shutdown()

    assert [str(error) for error in caught.value.exceptions] == [
        "flush failed",
        "shutdown failed",
    ]
    assert events == [
        "trace-force-flush",
        "meter-force-flush",
        "trace-shutdown",
        "meter-shutdown",
    ]


def test_real_telemetry_runtime_leaves_no_export_worker_threads() -> None:
    program = textwrap.dedent(
        """
        import json
        import threading

        from opentelemetry import metrics, trace

        from ai_chat.config import TelemetrySettings
        from ai_chat.telemetry import start_telemetry

        worker_names = {
            "OtelBatchSpanRecordProcessor",
            "OtelPeriodicExportingMetricReader",
        }
        runtime = start_telemetry(
            TelemetrySettings(
                api_key="test-key",
                host="127.0.0.1",
                port=1,
                insecure=True,
            )
        )
        started = sorted(
            thread.name for thread in threading.enumerate()
            if thread.name in worker_names
        )
        providers_installed = (
            trace.get_tracer_provider() is runtime.trace_provider
            and metrics.get_meter_provider() is runtime.meter_provider
        )
        runtime.shutdown()
        remaining = sorted(
            thread.name for thread in threading.enumerate()
            if thread.name in worker_names
        )
        print(json.dumps({
            "providers_installed": providers_installed,
            "started": started,
            "remaining": remaining,
        }))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip())
    assert result == {
        "providers_installed": True,
        "started": [
            "OtelBatchSpanRecordProcessor",
            "OtelPeriodicExportingMetricReader",
        ],
        "remaining": [],
    }


@pytest.mark.parametrize("preinstalled_provider", ["trace", "meter"])
def test_telemetry_provider_conflict_is_rejected_before_any_global_or_worker_change(
    preinstalled_provider: str,
) -> None:
    program = textwrap.dedent(
        f"""
        import json
        import threading

        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.trace import TracerProvider

        from ai_chat.config import TelemetrySettings
        from ai_chat.telemetry import start_telemetry

        worker_names = {{
            "OtelBatchSpanRecordProcessor",
            "OtelPeriodicExportingMetricReader",
        }}
        preinstalled_provider = {preinstalled_provider!r}
        if preinstalled_provider == "trace":
            owned_provider = TracerProvider()
            trace.set_tracer_provider(owned_provider)
            untouched_before = metrics.get_meter_provider()
        else:
            owned_provider = MeterProvider()
            metrics.set_meter_provider(owned_provider)
            untouched_before = trace.get_tracer_provider()

        conflict = False
        try:
            start_telemetry(
                TelemetrySettings(
                    api_key="test-key",
                    host="127.0.0.1",
                    port=1,
                    insecure=True,
                )
            )
        except RuntimeError as error:
            conflict = str(error) == "OpenTelemetry providers are already installed"

        untouched_after = (
            metrics.get_meter_provider()
            if preinstalled_provider == "trace"
            else trace.get_tracer_provider()
        )
        workers = sorted(
            thread.name for thread in threading.enumerate()
            if thread.name in worker_names
        )
        print(json.dumps({{
            "conflict": conflict,
            "untouched_same": untouched_after is untouched_before,
            "workers": workers,
        }}))
        owned_provider.shutdown()
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout.strip()) == {
        "conflict": True,
        "untouched_same": True,
        "workers": [],
    }


@pytest.mark.parametrize("value", ["yes", "1", "FALSE ", ""])
def test_telemetry_insecure_boolean_rejects_ambiguous_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_API_KEY", "key")
    monkeypatch.setenv("JUNJO_AI_STUDIO_INSECURE", value)
    with pytest.raises(ValueError, match="exactly true or false"):
        Settings.from_environment()


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_telemetry_port_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_API_KEY", "key")
    monkeypatch.setenv("JUNJO_AI_STUDIO_PORT", value)
    with pytest.raises(ValueError, match="JUNJO_AI_STUDIO_PORT"):
        Settings.from_environment()


def test_telemetry_boolean_and_port_accept_explicit_valid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_API_KEY", "key")
    monkeypatch.setenv("JUNJO_AI_STUDIO_INSECURE", "false")
    monkeypatch.setenv("JUNJO_AI_STUDIO_PORT", "443")
    settings = Settings.from_environment()
    assert settings.telemetry is not None
    assert settings.telemetry.insecure is False
    assert settings.telemetry.port == 443
