"""FastAPI entrypoint for an HTTP-rooted mixed OpenAI and Junjo trace."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from agents import RunConfig, Runner
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .application import (
    OPENAI_WORKFLOW_NAME,
    LocalPlaceInput,
    LocalPlaceOutput,
    build_openai_agent,
)
from .telemetry import TelemetryRuntime, start_telemetry

HEALTH_PATH = "/healthz"


def create_app(
    *,
    telemetry_factory: Callable[[], TelemetryRuntime] | None = None,
) -> FastAPI:
    """Build the HTTP example with telemetry owned by its ASGI lifespan."""

    resolved_telemetry_factory = telemetry_factory or start_telemetry

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        telemetry = resolved_telemetry_factory()
        try:
            yield
        finally:
            telemetry.close()

    app = FastAPI(title="Junjo + OpenAI Agents SDK Example", lifespan=lifespan)
    FastAPIInstrumentor.instrument_app(app, excluded_urls=HEALTH_PATH)

    @app.get(HEALTH_PATH)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/recommendations", response_model=LocalPlaceOutput)
    async def recommend(input_value: LocalPlaceInput) -> LocalPlaceOutput:
        result = await Runner.run(
            build_openai_agent(),
            input_value.message,
            run_config=RunConfig(workflow_name=OPENAI_WORKFLOW_NAME),
        )
        return LocalPlaceOutput(response=str(result.final_output))

    return app


app = create_app()
