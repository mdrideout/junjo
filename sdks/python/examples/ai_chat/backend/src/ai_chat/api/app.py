"""FastAPI construction with explicit application and telemetry lifetimes."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from junjo import AgentError

from ai_chat.bootstrap import ChatApplication
from ai_chat.config import TelemetrySettings
from ai_chat.domain.errors import ContactNotFoundError, ConversationNotFoundError
from ai_chat.telemetry import TelemetryRuntime, start_telemetry

from .routes import router
from .schemas import AgentErrorResponse


async def _close_lifespan_resources(
    application: ChatApplication,
    telemetry_runtime: TelemetryRuntime | None,
) -> None:
    application_close_error: BaseException | None = None
    try:
        await application.close()
    except BaseException as error:
        application_close_error = error

    try:
        if telemetry_runtime is not None:
            telemetry_runtime.shutdown()
    except BaseException as telemetry_shutdown_error:
        if application_close_error is not None:
            raise BaseExceptionGroup(
                "application and telemetry cleanup both failed",
                [application_close_error, telemetry_shutdown_error],
            ) from None
        raise

    if application_close_error is not None:
        raise application_close_error


def create_app(
    *,
    application: ChatApplication,
    cors_origins: tuple[str, ...] = (),
    telemetry: TelemetrySettings | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        telemetry_runtime: TelemetryRuntime | None = None
        try:
            if telemetry is not None:
                telemetry_runtime = start_telemetry(telemetry)
            await application.initialize()
            yield
        finally:
            await _close_lifespan_resources(application, telemetry_runtime)

    app = FastAPI(title="Junjo AI Chat Example", lifespan=lifespan)
    app.state.chat_application = application
    app.include_router(router)
    app.mount("/api/images", StaticFiles(directory=application.image_directory), name="images")
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(ConversationNotFoundError)
    @app.exception_handler(ContactNotFoundError)
    async def not_found(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(AgentError)
    async def agent_error(_: Request, error: AgentError) -> JSONResponse:
        response = AgentErrorResponse(
            detail=str(error),
            agent_run_id=error.run_id,
            termination_reason=error.termination_reason,
        )
        return JSONResponse(
            status_code=500,
            content=response.model_dump(mode="json"),
        )

    return app
