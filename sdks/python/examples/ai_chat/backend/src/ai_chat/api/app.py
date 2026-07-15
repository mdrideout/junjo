"""FastAPI construction with explicit application and telemetry lifetimes."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from junjo import AgentError
from junjo.agent import AgentModelError
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ai_chat.bootstrap import ChatApplication
from ai_chat.config import TelemetrySettings
from ai_chat.domain.errors import (
    ContactNotFoundError,
    ConversationNotFoundError,
    TurnExecutionError,
    TurnInProgressError,
    TurnNotFoundError,
)
from ai_chat.telemetry import TelemetryRuntime, start_telemetry

from .routes import router
from .schemas import TurnProblemResponse, TurnResponse


async def _close_lifespan_resources(
    application: ChatApplication | None,
    telemetry_runtime: TelemetryRuntime | None,
) -> None:
    application_close_error: BaseException | None = None
    try:
        if application is not None:
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
    application_factory: Callable[[], ChatApplication],
    image_directory: Path,
    cors_origins: tuple[str, ...] = (),
    telemetry: TelemetrySettings | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(running_app: FastAPI):
        telemetry_runtime: TelemetryRuntime | None = None
        application: ChatApplication | None = None
        try:
            if telemetry is not None:
                telemetry_runtime = start_telemetry(telemetry)
            application = application_factory()
            running_app.state.chat_application = application
            await application.initialize()
            yield
        finally:
            try:
                await _close_lifespan_resources(application, telemetry_runtime)
            finally:
                running_app.state.chat_application = None

    app = FastAPI(title="Junjo AI Chat Example", lifespan=lifespan)
    FastAPIInstrumentor.instrument_app(app)
    app.state.chat_application = None
    app.include_router(router)
    app.mount(
        "/api/images",
        StaticFiles(directory=image_directory, check_dir=False),
        name="images",
    )
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
    @app.exception_handler(TurnNotFoundError)
    async def not_found(request: Request, error: Exception) -> JSONResponse:
        return _problem(
            request=request,
            status=404,
            problem_type="resource-not-found",
            title="Resource not found",
            detail=str(error),
        )

    @app.exception_handler(TurnInProgressError)
    async def turn_conflict(request: Request, error: TurnInProgressError) -> JSONResponse:
        return _problem(
            request=request,
            status=409,
            problem_type="turn-in-progress",
            title="Conversation already has an active Turn",
            detail=str(error),
        )

    @app.exception_handler(TurnExecutionError)
    async def turn_execution_failed(request: Request, error: TurnExecutionError) -> JSONResponse:
        application = _application(request)
        turn = await application.store.get_turn(error.turn_id)
        cause = error.__cause__
        status = 502 if _cause_chain_contains(cause, AgentModelError) else 500
        return _problem(
            request=request,
            status=status,
            problem_type="turn-execution-failed",
            title="Turn execution failed",
            detail=turn.failure.detail if turn.failure is not None else str(error),
            turn=TurnResponse.from_domain(turn),
        )

    @app.exception_handler(AgentError)
    async def unowned_agent_error(request: Request, error: AgentError) -> JSONResponse:
        return _problem(
            request=request,
            status=502 if isinstance(error, AgentModelError) else 500,
            problem_type="agent-execution-failed",
            title="Agent execution failed",
            detail="Agent execution failed outside an admitted Turn.",
            agent_run_id=error.run_id,
            termination_reason=error.termination_reason,
        )

    return app


def _cause_chain_contains(
    error: BaseException | None,
    error_type: type[BaseException],
) -> bool:
    """Inspect explicit exception ownership without flattening its boundaries."""

    current = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, error_type):
            return True
        visited.add(id(current))
        current = current.__cause__
    return False


def _application(request: Request) -> ChatApplication:
    application = request.app.state.chat_application
    if not isinstance(application, ChatApplication):
        raise RuntimeError("Chat application state is not configured.")
    return application


def _problem(
    *,
    request: Request,
    status: int,
    problem_type: str,
    title: str,
    detail: str,
    turn: TurnResponse | None = None,
    agent_run_id: str | None = None,
    termination_reason: str | None = None,
) -> JSONResponse:
    references = turn.execution_references if turn is not None else None
    failure = turn.failure if turn is not None else None
    response = TurnProblemResponse(
        type=f"https://junjo.ai/problems/ai-chat/{problem_type}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        turn_id=turn.id if turn is not None else None,
        workflow_run_id=references.workflow_run_id if references is not None else None,
        agent_run_id=(references.agent_run_id if references is not None else agent_run_id),
        termination_reason=(failure.termination_reason if failure is not None else termination_reason),
        turn=turn,
    )
    return JSONResponse(
        status_code=status,
        content=response.model_dump(mode="json"),
        media_type="application/problem+json",
    )
