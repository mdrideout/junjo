"""Strict HTTP contract and explicit lifespan ownership tests."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx
import pytest
from junjo import ModelDriverBinding
from junjo.agent import (
    AgentAdmissionError,
    FinalOutputResponse,
    ToolCall,
    ToolCallsResponse,
)

from ai_chat.api.access_log import HealthCheckAccessLogFilter
from ai_chat.api.app import create_app
from ai_chat.api.schemas import MessageResponse
from ai_chat.bootstrap import ChatApplication, ProviderRuntime
from ai_chat.config import ModelProvider, Settings, TelemetrySettings
from ai_chat.telemetry import TelemetryRuntime
from conftest import make_harness, scripted_descriptor


@pytest.mark.asyncio
async def test_api_matches_the_greenfield_frontend_contract(tmp_path: Path) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "API response", "image": None})],
    )
    app = create_app(
        application_factory=lambda: harness.application,
        image_directory=harness.application.image_directory,
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/api/healthz")
            assert health.status_code == 204
            assert health.content == b""

            conversations = await client.get("/api/conversations")
            assert conversations.status_code == 200
            assert conversations.json() == {
                "conversations": [
                    {
                        "id": "demo",
                        "title": "Demo conversation",
                        "contact": {
                            "object_type": "ai_chat.contact",
                            "schema_version": 1,
                            "id": "contact-1",
                            "first_name": "Junjo",
                            "last_name": "Guide",
                            "sex": "female",
                            "age": 31,
                            "personality": {
                                "openness": 0.8,
                                "conscientiousness": 0.6,
                                "extraversion": 0.7,
                                "agreeableness": 0.8,
                                "neuroticism": 0.2,
                                "intelligence": 0.8,
                                "religiousness": 0.1,
                                "attractiveness": 0.8,
                                "trauma": 0.2,
                            },
                            "latitude": 40.6782,
                            "longitude": -73.9442,
                            "city": "Brooklyn",
                            "state": "NY",
                            "bio": "A deterministic application contact.",
                            "avatar_url": "/api/images/avatar-1.png",
                        },
                        "last_message_at": None,
                    }
                ]
            }

            config = await client.get("/api/config")
            assert config.status_code == 200
            assert config.json() == {
                "debug_enabled": False,
                "studio_ui_url": None,
                "service_namespace": "junjo.examples",
                "service_name": "ai-chat",
            }

            turn = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "Hello from the API"},
            )
            assert turn.status_code == 202
            admitted = turn.json()
            assert admitted["status"] == "admitted"
            payload = await _terminal_turn(client, admitted["id"])
            assert set(payload) == {
                "object_type",
                "schema_version",
                "id",
                "revision",
                "conversation_id",
                "sequence",
                "status",
                "context_policy",
                "user_message",
                "assistant_message",
                "execution_references",
                "failure",
                "created_at",
                "updated_at",
                "completed_at",
            }
            assert payload["object_type"] == "ai_chat.turn"
            assert payload["schema_version"] == 1
            assert payload["status"] == "completed"
            assert payload["conversation_id"] == "demo"
            assert payload["user_message"]["content"] == "Hello from the API"
            assert payload["assistant_message"]["content"] == "API response"
            assert payload["execution_references"]["workflow_run_id"]
            assert payload["execution_references"]["agent_run_id"]
            assert payload["failure"] is None
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

            turns = await client.get("/api/conversations/demo/turns")
            assert turns.status_code == 200
            assert turns.json() == {
                "conversation_id": "demo",
                "turns": [payload],
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


def test_health_check_access_log_filter_suppresses_only_health_probes() -> None:
    access_filter = HealthCheckAccessLogFilter()
    health_record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", "/api/healthz", "1.1", 204),
        exc_info=None,
    )
    config_record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", "/api/config", "1.1", 200),
        exc_info=None,
    )
    failed_health_record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", "/api/healthz", "1.1", 503),
        exc_info=None,
    )

    assert access_filter.filter(health_record) is False
    assert access_filter.filter(failed_health_record) is True
    assert access_filter.filter(config_record) is True


@pytest.mark.asyncio
async def test_health_check_returns_503_before_lifespan_initialization(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    app = create_app(
        application_factory=lambda: harness.application,
        image_directory=harness.application.image_directory,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/healthz")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_background_agent_failure_is_persisted_and_pollable(
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
    app = create_app(
        application_factory=lambda: harness.application,
        image_directory=harness.application.image_directory,
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            admitted = await client.post(
                "/api/conversations/demo/turns",
                json={"text": "Search history"},
            )
            assert admitted.status_code == 202
            body = await _terminal_turn(client, admitted.json()["id"])

    assert body["status"] == "failed"
    assert body["execution_references"]["workflow_run_id"]
    assert body["execution_references"]["agent_run_id"]
    assert body["failure"]["termination_reason"] == "tool_input_validation_error"
    assert body["failure"]["code"] == "agent_execution_failed"


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

    monkeypatch.setattr(harness.turns, "admit", fail_admission)
    app = create_app(
        application_factory=lambda: harness.application,
        image_directory=harness.application.image_directory,
    )
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
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "https://junjo.ai/problems/ai-chat/agent-execution-failed",
        "title": "Agent execution failed",
        "status": 500,
        "detail": "Agent execution failed outside an admitted Turn.",
        "instance": "/api/conversations/demo/turns",
        "turn_id": None,
        "workflow_run_id": None,
        "agent_run_id": "admission-run",
        "termination_reason": "internal_error",
        "turn": None,
    }


async def _terminal_turn(client: httpx.AsyncClient, turn_id: str) -> dict[str, object]:
    for _ in range(100):
        response = await client.get(f"/api/turns/{turn_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        await asyncio.sleep(0)
    raise AssertionError("Turn did not reach a terminal state.")


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
            contacts=source.contacts,
            images=source.images,
            image_directory=source.image_directory,
            provider_runtime=source.provider_runtime,
            debug=source.debug,
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


@pytest.mark.asyncio
async def test_application_factory_runs_inside_lifespan_and_closes_provider_once(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    harness = make_harness(tmp_path)
    assert harness.driver is not None

    async def close_provider() -> None:
        events.append("provider-close")

    harness.application.provider_runtime = ProviderRuntime(
        model=ModelDriverBinding.shared(
            descriptor=scripted_descriptor(),
            driver=harness.driver,
        ),
        language=harness.language,
        images=harness.images,
        _close_client=close_provider,
    )
    application = RecordingApplication(source=harness.application, events=events)

    def application_factory() -> ChatApplication:
        asyncio.get_running_loop()
        events.append("application-factory")
        return application

    app = create_app(
        application_factory=application_factory,
        image_directory=application.image_directory,
    )
    assert events == []

    async with app.router.lifespan_context(app):
        assert events == ["application-factory", "application-initialize"]

    assert events == [
        "application-factory",
        "application-initialize",
        "application-close",
        "provider-close",
    ]


@pytest.mark.asyncio
async def test_application_attempts_provider_cleanup_when_store_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    harness = make_harness(tmp_path)
    assert harness.driver is not None

    async def fail_store_close() -> None:
        events.append("store-close")
        raise RuntimeError("store close failed")

    async def close_provider() -> None:
        events.append("provider-close")

    monkeypatch.setattr(harness.store, "close", fail_store_close)
    harness.application.provider_runtime = ProviderRuntime(
        model=ModelDriverBinding.shared(
            descriptor=scripted_descriptor(),
            driver=harness.driver,
        ),
        language=harness.language,
        images=harness.images,
        _close_client=close_provider,
    )

    with pytest.raises(RuntimeError, match="store close failed"):
        await harness.application.close()

    assert events == ["store-close", "provider-close"]


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
    app = create_app(
        application_factory=lambda: application,
        image_directory=application.image_directory,
        telemetry=settings,
    )

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
    app = create_app(
        application_factory=lambda: application,
        image_directory=application.image_directory,
        telemetry=settings,
    )

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
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    settings = Settings.from_environment()
    assert settings.telemetry is not None
    assert settings.telemetry.insecure is False
    assert settings.telemetry.port == 443


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "not-a-number"])
def test_provider_timeout_rejects_non_positive_or_non_finite_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("AI_CHAT_PROVIDER_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="AI_CHAT_PROVIDER_TIMEOUT_SECONDS"):
        Settings.from_environment()


@pytest.mark.parametrize(
    ("provider", "required_key"),
    [("gemini", "GEMINI_API_KEY"), ("grok", "XAI_API_KEY")],
)
def test_live_provider_selection_requires_its_own_key(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    required_key: str,
) -> None:
    monkeypatch.setenv("AI_CHAT_MODEL_PROVIDER", provider)
    monkeypatch.delenv(required_key, raising=False)

    with pytest.raises(ValueError, match=required_key):
        Settings.from_environment()


def test_gemini_is_the_explicit_default_and_requires_its_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_CHAT_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings.from_environment()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    settings = Settings.from_environment()
    assert settings.model_provider is ModelProvider.GEMINI
    assert settings.gemini_api_key == "gemini-key"
