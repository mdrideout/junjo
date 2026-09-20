"""Loopback MCP bridge and Codex OTLP/HTTP JSON receiver."""

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .codex_telemetry import CodexTelemetry
from .runtime import Runtime


class JsonSpans(SpanExporter):
    """Optional local evidence artifact, containing only exported Junjo-scope spans."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a")

    def export(self, spans):
        for span in spans:
            self.file.write(span.to_json(indent=None) + "\n")
        self.file.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.file.close()


def create_server(runtime: Runtime, telemetry: CodexTelemetry, provider: TracerProvider) -> FastMCP:
    mcp = FastMCP("Junjo Coding Agents", stateless_http=True, json_response=True)

    @mcp.tool()
    def start_execution(capture: bool = False) -> dict[str, Any]:
        """Start a FunctionReview batch. capture=True explicitly enables scoped diagnostics."""
        return runtime.start(capture)

    @mcp.tool()
    async def start_review(execution_id: str, fixture: str) -> dict[str, Any]:
        """Start one worker's real Junjo workflow; fixture is buggy or correct. Returns the first reasoning step."""
        return await runtime.review(execution_id, fixture)

    @mcp.tool()
    async def complete_step(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Submit your reasoning result matching output_schema. Returns the next step or completed workflow.

        Print the complete tool response unchanged so the host telemetry retains its completion receipt.
        Perform one step per model response. Reason about the returned next step in a NEW model response.
        """
        return await runtime.complete(request_id, result)

    @mcp.tool()
    async def finish_execution(execution_id: str, cancel: bool = False) -> dict[str, Any]:
        """Close a batch after workers finish, or cancel=True to interrupt its unfinished workflows."""
        return await runtime.finish(execution_id, cancel)

    @mcp.tool()
    def execution_status(execution_id: str) -> dict[str, Any]:
        """Return workflow results and observed model-span coverage. Zero model spans means unproven capture."""
        return runtime.status(execution_id)

    @mcp.custom_route("/v1/traces", methods=["POST"])
    async def traces(request: Request):
        telemetry.receive_traces(await request.json())
        return JSONResponse({})

    @mcp.custom_route("/v1/logs", methods=["POST"])
    async def logs(request: Request):
        telemetry.receive_logs(await request.json())
        return JSONResponse({})

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request):
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/evidence/{execution_id}", methods=["GET"])
    async def evidence(request: Request):
        return JSONResponse(runtime.status(request.path_params["execution_id"]))

    @mcp.custom_route("/flush", methods=["POST"])
    async def flush(request: Request):
        telemetry.reconcile()
        ok = await asyncio.to_thread(provider.force_flush)
        return JSONResponse({"flushed": ok})

    return mcp


def create_app(runtime: Runtime, telemetry: CodexTelemetry, provider: TracerProvider):
    mcp = create_server(runtime, telemetry, provider)
    app = mcp.streamable_http_app()
    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        # FastMCP's server lifespan runs per stateless request. Execution and
        # exporter ownership belong to the ASGI process, not an MCP session.
        try:
            async with mcp_lifespan(app):
                yield
        finally:
            await runtime.shutdown()
            provider.shutdown()

    app.router.lifespan_context = lifespan
    app.user_middleware.append(Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"]))
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=26156)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--spans-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    # The execution's explicit capture choice owns sampling, even if the
    # user's environment configures an unrelated global OTel sampler.
    provider = TracerProvider(
        resource=Resource.create({"service.name": "junjo-coding-agents"}), sampler=ParentBased(ALWAYS_ON)
    )
    if args.spans_file:
        provider.add_span_processor(SimpleSpanProcessor(JsonSpans(args.spans_file)))
    endpoint = os.environ.get("JUNJO_AI_STUDIO_OTLP_ENDPOINT")
    if endpoint:
        exporter = JunjoOtelExporter(
            endpoint=endpoint,
            api_key=os.environ["JUNJO_AI_STUDIO_API_KEY"],
            insecure=os.environ.get("JUNJO_AI_STUDIO_OTLP_INSECURE", "false").lower() == "true",
        )
        provider.add_span_processor(exporter.span_processor)
    elif not args.spans_file:
        parser.error("Configure Studio export or --spans-file so capture has an observable destination")
    trace.set_tracer_provider(provider)
    runtime = Runtime(provider.get_tracer("junjo.coding_agents"))
    app = create_app(runtime, CodexTelemetry(runtime), provider)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
