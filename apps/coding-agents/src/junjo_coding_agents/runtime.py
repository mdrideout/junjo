"""In-memory work handoff. Junjo retains ownership of graph traversal and state."""

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from junjo import ExecutionCorrelation
from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags
from pydantic import BaseModel

from .workflow import FIXTURES, ReviewState, build_review


def identifier() -> str:
    return secrets.token_hex(16)


@dataclass
class Work:
    id: str
    run: "ReviewRun"
    instructions: str
    state: ReviewState
    output_type: type[BaseModel]
    context: context.Context
    future: asyncio.Future[BaseModel]
    submitted: bool = False
    issued_ns: int = field(default_factory=time.time_ns)
    receipt: str | None = None
    model_span_ids: set[str] = field(default_factory=set)

    def describe(self) -> dict[str, Any]:
        return {
            "status": "work",
            "execution_id": self.run.execution.id,
            "run_id": self.run.id,
            "request_id": self.id,
            "instructions": self.instructions,
            "input": self.state.model_dump(mode="json"),
            "output_schema": self.output_type.model_json_schema(),
        }


@dataclass
class Execution:
    id: str
    capture: bool
    span: trace.Span
    runs: dict[str, "ReviewRun"] = field(default_factory=dict)
    status: str = "running"


class ReviewRun:
    def __init__(self, runtime: "Runtime", execution: Execution, fixture: str):
        self.runtime = runtime
        self.execution = execution
        self.fixture = fixture
        self.id = identifier()
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.status = "running"
        self.result: dict[str, Any] | None = None
        self.task: asyncio.Task[None] | None = None

    async def request(self, instructions: str, state: ReviewState, output_type: type[BaseModel]) -> BaseModel:
        work = Work(
            identifier(),
            self,
            instructions,
            state,
            output_type,
            context.get_current(),
            asyncio.get_running_loop().create_future(),
        )
        self.runtime.work[work.id] = work
        await self.queue.put(work.describe())
        return await work.future

    async def execute(self) -> None:
        parent = trace.set_span_in_context(self.execution.span)
        try:
            with self.runtime.tracer.start_as_current_span(
                "Codex worker",
                context=parent,
                attributes={
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": "Codex",
                    "coding_agent.run.id": self.id,
                    "coding_agent.fixture": self.fixture,
                },
            ):
                result = await build_review(self, self.fixture).execute(
                    correlation=ExecutionCorrelation(type="coding-agent-execution", id=self.execution.id)
                )
                self.status = "completed"
                self.result = {
                    "status": self.status,
                    "run_id": self.id,
                    "workflow_run_id": result.run_id,
                    "state": result.state.model_dump(mode="json"),
                }
        except asyncio.CancelledError:
            self.status = "cancelled"
            self.result = {"status": self.status, "run_id": self.id}
            raise
        except Exception as error:
            self.status = "failed"
            self.result = {
                "status": self.status,
                "run_id": self.id,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        finally:
            await self.queue.put(self.result or {"status": "failed", "run_id": self.id})


class Runtime:
    def __init__(self, tracer: trace.Tracer):
        self.tracer = tracer
        self.executions: dict[str, Execution] = {}
        self.work: dict[str, Work] = {}

    def start(self, capture: bool) -> dict[str, Any]:
        execution_id = identifier()
        # A valid unsampled parent suppresses *native SDK* spans too. An invalid
        # no-op span would instead cause the SDK's sampler to start a new trace.
        parent = (
            trace.set_span_in_context(
                NonRecordingSpan(
                    SpanContext(
                        trace_id=secrets.randbits(128),
                        span_id=secrets.randbits(64),
                        is_remote=False,
                        trace_flags=TraceFlags(TraceFlags.DEFAULT),
                    )
                )
            )
            if not capture
            else context.Context()
        )
        span = self.tracer.start_span(
            "Review example functions",
            context=parent,
            attributes={
                "coding_agent.execution.id": execution_id,
                "coding_agent.host": "codex",
                "coding_agent.workflow": "FunctionReview",
                "coding_agent.capture": capture,
            },
        )
        execution = Execution(execution_id, capture, span)
        self.executions[execution_id] = execution
        return {
            "execution_id": execution_id,
            "capture": capture,
            "trace_id": format(span.get_span_context().trace_id, "032x") if capture else None,
        }

    async def review(self, execution_id: str, fixture: str) -> dict[str, Any]:
        execution = self.executions[execution_id]
        if execution.status != "running":
            raise ValueError("Execution is already closed")
        if fixture not in FIXTURES:
            raise ValueError("fixture must be 'buggy' or 'correct'")
        run = ReviewRun(self, execution, fixture)
        execution.runs[run.id] = run
        run.task = asyncio.create_task(run.execute())
        return await run.queue.get()

    async def complete(self, request_id: str, result: dict[str, Any]) -> dict[str, Any]:
        work = self.work[request_id]
        if work.submitted or work.future.done() or work.run.execution.status != "running":
            raise ValueError("Work request is no longer pending")
        validated = work.output_type.model_validate(result)
        work.submitted = True
        work.receipt = identifier()
        work.future.set_result(validated)
        return {**await work.run.queue.get(), "completed_request_id": work.id, "receipt": work.receipt}

    async def finish(self, execution_id: str, cancel: bool = False) -> dict[str, Any]:
        execution = self.executions[execution_id]
        if execution.status != "running":
            raise ValueError("Execution is already closed")
        active = [r.task for r in execution.runs.values() if r.task and not r.task.done()]
        if active and not cancel:
            raise ValueError("Workers are still running; complete them or explicitly cancel")
        if cancel:
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)
        execution.status = (
            "cancelled"
            if cancel
            else ("failed" if any(r.status == "failed" for r in execution.runs.values()) else "completed")
        )
        execution.span.set_attribute("coding_agent.outcome", execution.status)
        if execution.status == "failed":
            execution.span.set_status(Status(StatusCode.ERROR))
        execution.span.end()
        return self.status(execution_id)

    def status(self, execution_id: str) -> dict[str, Any]:
        execution = self.executions[execution_id]
        return {
            "execution_id": execution.id,
            "status": execution.status,
            "capture": execution.capture,
            "runs": [r.result or {"run_id": r.id, "status": r.status} for r in execution.runs.values()],
            "work": [
                {"request_id": w.id, "submitted": w.submitted, "model_spans": len(w.model_span_ids)}
                for w in self.work.values()
                if w.run.execution is execution
            ],
        }

    async def shutdown(self) -> None:
        for execution in self.executions.values():
            if execution.status == "running":
                await self.finish(execution.id, cancel=True)
