"""Shared pytest fixtures for deliberate credentialed AI Chat eval runs."""

from collections.abc import Iterator

import pytest

from ai_chat.config import Settings
from ai_chat.telemetry import TelemetryRuntime, start_telemetry


@pytest.fixture(scope="session")
def live_telemetry() -> Iterator[TelemetryRuntime | None]:
    """Export live eval evidence when Studio telemetry is configured."""

    settings = Settings.from_environment()
    runtime = start_telemetry(settings.telemetry) if settings.telemetry is not None else None
    try:
        yield runtime
    finally:
        if runtime is not None:
            runtime.shutdown()
