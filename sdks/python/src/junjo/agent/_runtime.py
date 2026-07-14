"""Isolated, bounded, provider-neutral Agent execution loop."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypedDict, TypeVar, cast

from opentelemetry import trace
from opentelemetry.trace import Span

from .._identity import (
    ActiveExecutableIdentity,
    ExecutableType,
    ParentExecutableIdentity,
    active_executable_identity,
    get_active_executable_identity,
)
from .._json import freeze_json, thaw_json
from .._lifecycle import AgentLifecycleIdentity, LifecycleDispatcher, PreparedHookEvent
from .._terminal import drain_terminal_work
from ..correlation import (
    ExecutionCorrelation,
    _active_execution_correlation,
    _resolve_execution_correlation,
    _set_correlation_span_attributes,
)
from ..telemetry.diagnostics import (
    cancellation_reason,
    error_type,
    exception_message,
)
from ..telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME
from ..telemetry.payload import set_full_payload
from ..telemetry.span_lifecycle import (
    get_span_identifiers,
    mark_span_cancelled,
    mark_span_failed,
    record_span_exception,
)
from ..util import generate_safe_id
from ._boundary import validate_and_detach
from ._state import AgentState, AgentStore, initial_agent_state, snapshot_agent_state
from ._telemetry import (
    diagnostic_candidate,
    finalize_agent_counts,
    initialize_agent_span,
    initialize_model_span,
    initialize_tool_span,
    record_candidate,
    record_model_response,
    record_unavailable,
)
from .errors import (
    AgentAdmissionError,
    AgentExecutionError,
    AgentHistoryValidationError,
    AgentInputValidationError,
    AgentInternalError,
    AgentInvocationError,
    AgentLimitExceededError,
    AgentModelError,
    AgentModelResponseError,
    AgentOutputValidationError,
    AgentToolError,
    AgentToolInputValidationError,
    AgentToolOutputValidationError,
    AgentUnknownToolError,
)
from .json import JsonValue
from .messages import (
    AgentInputMessage,
    AgentMessage,
    AssistantOutputMessage,
    AssistantToolCallsMessage,
    FinalOutputResponse,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolCallsResponse,
    ToolDefinition,
    ToolResultMessage,
    message_to_json,
    normalize_model_response,
    validate_history,
)
from .model_driver import ModelDriver
from .result import AgentExecutionResult, AgentUsage
from .tool import AgentRunContext, Tool, ToolService

if TYPE_CHECKING:
    from .definition import Agent

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
DependenciesT = TypeVar("DependenciesT")


class _ErrorIdentity(TypedDict):
    agent_key: str
    definition_id: str
    structural_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class _PreparedToolCall:
    tool: Tool
    call: ToolCall
    ordinal: int
    typed_input: object
    normalized_arguments: JsonValue


@dataclass(frozen=True, slots=True)
class _PreparedCompletion(Generic[OutputT]):
    typed_output: OutputT
    normalized_output: JsonValue


class _AgentRun(Generic[InputT, OutputT, DependenciesT]):
    """Mutable state local to exactly one admitted Agent execution."""

    def __init__(
        self,
        *,
        agent: Agent[InputT, OutputT, DependenciesT],
        run_id: str,
        dependencies: DependenciesT,
        transcript: Sequence[AgentMessage],
        store: AgentStore,
        dispatcher: LifecycleDispatcher,
        initial_state: AgentState,
    ) -> None:
        self.agent = agent
        self.run_id = run_id
        self.dependencies = dependencies
        self.transcript = list(transcript)
        self.store = store
        self.dispatcher = dispatcher
        self._last_known_state = initial_state.model_copy(deep=True)
        self.usage = AgentUsage()
        self.operation_count = 0
        self._driver: ModelDriver | None = None
        self._tool_services: dict[str, ToolService] = {}
        self._tools_by_name = {tool.name: tool for tool in agent.tools}
        self._seen_call_ids = {
            call.id
            for message in transcript
            if isinstance(message, AssistantToolCallsMessage)
            for call in message.tool_calls
        }

    async def _get_state(self) -> AgentState:
        """Read and remember detached evidence without making it recursive."""

        state = await self.store.get_state()
        self._last_known_state = state.model_copy(deep=True)
        return state

    def _get_last_known_state(self) -> AgentState:
        """Return truthful emergency evidence without awaiting failed machinery."""

        try:
            state = self.store._get_last_known_state()
        except Exception:
            state = self._last_known_state
        return state.model_copy(deep=True)

    async def run(self) -> _PreparedCompletion[OutputT]:
        while True:
            response = await self._request_model()
            if isinstance(response, FinalOutputResponse):
                return await self._complete(response)
            await self._run_tool_batch(response)

    async def _request_model(self) -> ModelResponse:
        state = await self._get_state()
        ordinal = state.model_request_count + 1
        if ordinal > self.agent.limits.model_requests:
            raise AgentLimitExceededError(
                "Agent model-request limit was exhausted before another request could start.",
                **self._error_identity(),
                state=snapshot_agent_state(state),
                limit_kind="model_requests",
                limit=self.agent.limits.model_requests,
                attempted_count=ordinal,
            )

        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        candidate_evidence_recorded = [False]
        with tracer.start_as_current_span(
            f"model request {ordinal}",
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                revision = await self.store.record_model_start(ordinal)
            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                raise

            request = ModelRequest(
                agent_key=self.agent.key,
                run_id=self.run_id,
                ordinal=ordinal,
                instructions=self.agent.instructions,
                messages=self.transcript,
                tools=[
                    ToolDefinition(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        output_schema=tool.output_schema,
                    )
                    for tool in self.agent.tools
                ],
                output_schema=self.agent.output_schema,
            )
            sequence = self.operation_count + 1
            initialize_model_span(
                span,
                agent=self.agent,
                run_id=self.run_id,
                sequence=sequence,
                ordinal=ordinal,
            )
            span.set_attribute("junjo.agent.model_request.state_revision", revision)
            set_full_payload(span, "junjo.agent.model.request", request.to_json())
            self.operation_count = sequence

            with _operation_cancellation(
                span,
                availability_root="junjo.agent.model.response_candidate.available",
                evidence_recorded=candidate_evidence_recorded,
            ):
                try:
                    driver = self._get_driver()
                    candidate = await driver.request(request)
                except asyncio.CancelledError as exc:
                    record_unavailable(
                        span,
                        availability_root="junjo.agent.model.response_candidate.available",
                        reason="cancelled",
                    )
                    candidate_evidence_recorded[0] = True
                    mark_span_cancelled(span, exc)
                    raise
                except Exception as exc:
                    record_unavailable(
                        span,
                        availability_root="junjo.agent.model.response_candidate.available",
                        reason="not_returned",
                    )
                    candidate_evidence_recorded[0] = True
                    error = AgentModelError(
                        "ModelDriver failed while producing a normalized response.",
                        **self._error_identity(),
                        state=snapshot_agent_state(await self._get_state()),
                    )
                    mark_span_failed(span, error)
                    record_span_exception(span, error)
                    raise error from exc

                normalized_candidate = record_candidate(
                    span,
                    availability_root="junjo.agent.model.response_candidate.available",
                    payload_root="junjo.agent.model.response_candidate",
                    candidate=candidate,
                )
                candidate_evidence_recorded[0] = True
                try:
                    response = normalize_model_response(
                        normalized_candidate if normalized_candidate is not None else candidate
                    )
                    self._validate_new_call_ids(response)
                    if isinstance(response, ToolCallsResponse):
                        _require_agent_state_message_capacity(
                            AssistantToolCallsMessage(
                                tool_calls=response.tool_calls,
                                assistant_text=response.assistant_text,
                            )
                        )
                    updated_usage = self.usage.add(response.usage)
                    await self.store.validate_model_response(response, updated_usage)
                except Exception as exc:
                    error = AgentModelResponseError(
                        "ModelDriver returned an invalid normalized response.",
                        **self._error_identity(),
                        state=snapshot_agent_state(await self._get_state()),
                    )
                    mark_span_failed(span, error)
                    record_span_exception(span, error)
                    raise error from exc

                await self.store.record_model_response(response, updated_usage)
                self.usage = updated_usage
                record_model_response(span, response)
                if isinstance(response, ToolCallsResponse):
                    self.transcript.append(
                        AssistantToolCallsMessage(
                            tool_calls=response.tool_calls,
                            assistant_text=response.assistant_text,
                        )
                    )
                    self._seen_call_ids.update(call.id for call in response.tool_calls)
                return response

    def _get_driver(self) -> ModelDriver:
        if self._driver is not None:
            return self._driver
        binding = self.agent.model
        if binding.shared_driver is not None:
            self._driver = binding.shared_driver
        else:
            assert binding.factory is not None
            self._driver = binding.factory()
        if not callable(getattr(self._driver, "request", None)):
            raise TypeError("ModelDriver factory product must implement async request().")
        return self._driver

    def _validate_new_call_ids(self, response: ModelResponse) -> None:
        if not isinstance(response, ToolCallsResponse):
            return
        seen = set(self._seen_call_ids)
        for call in response.tool_calls:
            if call.id in seen:
                raise ValueError(f"Tool call id is not unique within this run: {call.id}")
            seen.add(call.id)

    async def _run_tool_batch(self, response: ToolCallsResponse) -> None:
        state = await self._get_state()
        batch_size = len(response.tool_calls)
        attempted = state.tool_call_admitted_count + batch_size
        ordinal_start = state.tool_call_requested_count - batch_size + 1
        if attempted > self.agent.limits.tool_calls:
            raise AgentLimitExceededError(
                "Agent Tool-call limit rejected the complete requested batch.",
                **self._error_identity(),
                state=snapshot_agent_state(state),
                limit_kind="tool_calls",
                limit=self.agent.limits.tool_calls,
                attempted_count=attempted,
                requested_batch_size=batch_size,
            )

        prepared: list[_PreparedToolCall] = []
        for index, call in enumerate(response.tool_calls):
            ordinal = ordinal_start + index
            tool = self._tools_by_name.get(call.name)
            if tool is None:
                raise AgentUnknownToolError(
                    f"Model requested unknown Tool {call.name!r}.",
                    **self._error_identity(),
                    state=snapshot_agent_state(await self._get_state()),
                    tool_name=call.name,
                    tool_call_id=call.id,
                    call_ordinal=ordinal,
                )
            try:
                typed, normalized = validate_and_detach(
                    tool.input_adapter,
                    thaw_json(call.arguments),
                )
            except Exception as exc:
                error = await self._record_invalid_tool_arguments(
                    tool=tool,
                    call=call,
                    ordinal=ordinal,
                )
                raise error from exc
            prepared.append(
                _PreparedToolCall(
                    tool=tool,
                    call=call,
                    ordinal=ordinal,
                    typed_input=typed,
                    normalized_arguments=thaw_json(normalized),
                )
            )

        await self.store.admit_tool_batch([item.call.id for item in prepared])
        for item in prepared:
            await self._execute_tool(item)

    async def _record_invalid_tool_arguments(
        self,
        *,
        tool: Tool,
        call: ToolCall,
        ordinal: int,
    ) -> AgentToolInputValidationError:
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        candidate_evidence_recorded = [False]
        with tracer.start_as_current_span(
            f"tool {tool.name}",
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                revision_before = await self.store._get_store_revision()
            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                raise

            sequence = self.operation_count + 1
            initialize_tool_span(
                span,
                agent_key=self.agent.key,
                run_id=self.run_id,
                sequence=sequence,
                tool=tool,
                call_id=call.id,
                call_ordinal=ordinal,
                requested_arguments=thaw_json(call.arguments),
            )
            span.set_attribute(
                "junjo.agent.tool.state_revision.before",
                revision_before,
            )
            self.operation_count = sequence

            with _operation_cancellation(
                span,
                availability_root="junjo.agent.tool.result_candidate.available",
                evidence_recorded=candidate_evidence_recorded,
            ):
                record_unavailable(
                    span,
                    availability_root="junjo.agent.tool.result_candidate.available",
                    reason="not_invoked",
                )
                candidate_evidence_recorded[0] = True
                error = AgentToolInputValidationError(
                    f"Arguments for Tool {tool.name!r} failed declared validation.",
                    **self._error_identity(),
                    state=snapshot_agent_state(await self._get_state()),
                    tool_name=tool.name,
                    tool_call_id=call.id,
                    call_ordinal=ordinal,
                )
                mark_span_failed(span, error)
                record_span_exception(span, error)
                return error

    async def _execute_tool(self, item: _PreparedToolCall) -> None:
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        candidate_evidence_recorded = [False]
        with tracer.start_as_current_span(
            f"tool {item.tool.name}",
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                revision_before = await self.store._get_store_revision()
            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                raise

            try:
                service = self._get_tool_service(item.tool)
            except Exception as exc:
                self._publish_tool_operation(
                    span,
                    item=item,
                    revision_before=revision_before,
                )
                with _operation_cancellation(
                    span,
                    availability_root="junjo.agent.tool.result_candidate.available",
                    evidence_recorded=candidate_evidence_recorded,
                ):
                    record_unavailable(
                        span,
                        availability_root="junjo.agent.tool.result_candidate.available",
                        reason="not_invoked",
                    )
                    candidate_evidence_recorded[0] = True
                    error = await self._tool_error(
                        AgentToolError,
                        item,
                        f"Tool {item.tool.name!r} service factory failed.",
                    )
                    mark_span_failed(span, error)
                    record_span_exception(span, error)
                    raise error from exc

            try:
                revision_before = await self.store.record_tool_started()
            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                raise

            self._publish_tool_operation(
                span,
                item=item,
                revision_before=revision_before,
            )

            with _operation_cancellation(
                span,
                availability_root="junjo.agent.tool.result_candidate.available",
                evidence_recorded=candidate_evidence_recorded,
            ):
                context = AgentRunContext(
                    dependencies=self.dependencies,
                    agent_key=self.agent.key,
                    definition_id=self.agent.definition_id,
                    run_id=self.run_id,
                    tool_call_id=item.call.id,
                    call_ordinal=item.ordinal,
                )
                try:
                    candidate = await service(item.typed_input, context)
                except asyncio.CancelledError as exc:
                    record_unavailable(
                        span,
                        availability_root="junjo.agent.tool.result_candidate.available",
                        reason="cancelled",
                    )
                    candidate_evidence_recorded[0] = True
                    mark_span_cancelled(span, exc)
                    raise
                except Exception as exc:
                    record_unavailable(
                        span,
                        availability_root="junjo.agent.tool.result_candidate.available",
                        reason="service_failed",
                    )
                    candidate_evidence_recorded[0] = True
                    error = await self._tool_error(
                        AgentToolError,
                        item,
                        f"Tool {item.tool.name!r} service failed.",
                    )
                    mark_span_failed(span, error)
                    record_span_exception(span, error)
                    raise error from exc

                normalized_candidate = diagnostic_candidate(candidate)
                if normalized_candidate is not None:
                    record_candidate(
                        span,
                        availability_root="junjo.agent.tool.result_candidate.available",
                        payload_root="junjo.agent.tool.result_candidate",
                        candidate=normalized_candidate,
                    )
                    candidate_evidence_recorded[0] = True
                try:
                    _typed_result, normalized = validate_and_detach(
                        item.tool.output_adapter,
                        normalized_candidate if normalized_candidate is not None else candidate,
                    )
                    normalized_result = thaw_json(normalized)
                    _require_agent_state_message_capacity(
                        ToolResultMessage(
                            tool_call_id=item.call.id,
                            tool_name=item.tool.name,
                            result=normalized_result,
                        )
                    )
                    await self.store.validate_tool_result(
                        call_id=item.call.id,
                        tool_name=item.tool.name,
                        result=normalized_result,
                    )
                except Exception as exc:
                    if normalized_candidate is None:
                        record_unavailable(
                            span,
                            availability_root=("junjo.agent.tool.result_candidate.available"),
                            reason="not_json_serializable",
                        )
                        candidate_evidence_recorded[0] = True
                    error = await self._tool_error(
                        AgentToolOutputValidationError,
                        item,
                        f"Tool {item.tool.name!r} output failed declared validation.",
                    )
                    mark_span_failed(span, error)
                    record_span_exception(span, error)
                    raise error from exc

                if normalized_candidate is None:
                    record_candidate(
                        span,
                        availability_root="junjo.agent.tool.result_candidate.available",
                        payload_root="junjo.agent.tool.result_candidate",
                        candidate=normalized_result,
                    )
                    candidate_evidence_recorded[0] = True
                revision_after = await self.store.record_tool_result(
                    call_id=item.call.id,
                    tool_name=item.tool.name,
                    result=normalized_result,
                )
                set_full_payload(span, "junjo.agent.tool.result", normalized_result)
                span.set_attribute(
                    "junjo.agent.tool.state_revision.after",
                    revision_after,
                )
                self.transcript.append(
                    ToolResultMessage(
                        tool_call_id=item.call.id,
                        tool_name=item.tool.name,
                        result=normalized_result,
                    )
                )

    def _publish_tool_operation(
        self,
        span: Span,
        *,
        item: _PreparedToolCall,
        revision_before: int,
    ) -> None:
        """Publish one Tool operation only after its required start evidence exists."""

        sequence = self.operation_count + 1
        initialize_tool_span(
            span,
            agent_key=self.agent.key,
            run_id=self.run_id,
            sequence=sequence,
            tool=item.tool,
            call_id=item.call.id,
            call_ordinal=item.ordinal,
            requested_arguments=thaw_json(item.call.arguments),
        )
        span.set_attribute(
            "junjo.agent.tool.state_revision.before",
            revision_before,
        )
        set_full_payload(
            span,
            "junjo.agent.tool.arguments",
            item.normalized_arguments,
        )
        self.operation_count = sequence

    def _get_tool_service(self, tool: Tool) -> ToolService:
        existing = self._tool_services.get(tool.name)
        if existing is not None:
            return existing
        if tool.shared_service is not None:
            service = tool.shared_service
        else:
            assert tool.factory is not None
            service = tool.factory()
        if not callable(service):
            raise TypeError("Tool service factory product must be callable.")
        self._tool_services[tool.name] = service
        return service

    async def _complete(
        self,
        response: FinalOutputResponse,
    ) -> _PreparedCompletion[OutputT]:
        try:
            typed_output, normalized = validate_and_detach(
                self.agent.output_adapter,
                thaw_json(response.output),
            )
            normalized_output = thaw_json(normalized)
            _require_agent_state_message_capacity(AssistantOutputMessage(normalized_output))
            await self.store.validate_success(normalized_output)
        except Exception as exc:
            error = AgentOutputValidationError(
                "Final Agent output failed declared validation.",
                **self._error_identity(),
                state=snapshot_agent_state(await self._get_state()),
            )
            raise error from exc
        return _PreparedCompletion(
            typed_output=cast(OutputT, typed_output),
            normalized_output=normalized_output,
        )

    async def _tool_error(
        self,
        error_type: type[AgentToolError] | type[AgentToolOutputValidationError],
        item: _PreparedToolCall,
        message: str,
    ) -> AgentToolError | AgentToolOutputValidationError:
        return error_type(
            message,
            **self._error_identity(),
            state=snapshot_agent_state(await self._get_state()),
            tool_name=item.tool.name,
            tool_call_id=item.call.id,
            call_ordinal=item.ordinal,
        )

    def _error_identity(self) -> _ErrorIdentity:
        return {
            "agent_key": self.agent.key,
            "definition_id": self.agent.definition_id,
            "structural_id": self.agent.structural_id,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class _AdmittedRun(Generic[InputT, OutputT, DependenciesT]):
    runtime: _AgentRun[InputT, OutputT, DependenciesT]
    lifecycle_identity: AgentLifecycleIdentity
    active_identity: ActiveExecutableIdentity


@dataclass(frozen=True, slots=True)
class _ExecutionOutcome(Generic[OutputT]):
    result: AgentExecutionResult[OutputT] | None = None
    error: AgentInvocationError | AgentExecutionError | None = None
    cancellation: asyncio.CancelledError | None = None
    terminal_delivery_cancellation: asyncio.CancelledError | None = None


async def execute_agent(
    agent: Agent[InputT, OutputT, DependenciesT],
    *,
    input: object,
    dependencies: DependenciesT,
    history: Sequence[AgentMessage],
    correlation: ExecutionCorrelation | None,
) -> AgentExecutionResult[OutputT]:
    """Create identity first, admit typed boundaries, then run one isolated loop."""

    effective_correlation = _resolve_execution_correlation(correlation)
    run_id = generate_safe_id()
    active_parent = get_active_executable_identity()
    parent = active_parent.as_parent() if active_parent is not None else None
    tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
    with _active_execution_correlation(effective_correlation), tracer.start_as_current_span(
        agent.name,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        initialize_agent_span(span, agent=agent, run_id=run_id, parent=parent)
        _set_correlation_span_attributes(span, effective_correlation)
        try:
            normalized_input, detached_history = _validate_invocation(
                agent=agent,
                run_id=run_id,
                span=span,
                input=input,
                history=history,
            )
        except AgentInvocationError as error:
            _record_invocation_failure(span, error)
            outcome: _ExecutionOutcome[OutputT] = _ExecutionOutcome(error=error)
        else:
            try:
                admitted = _admit_run(
                    agent=agent,
                    run_id=run_id,
                    parent=parent,
                    span=span,
                    dependencies=dependencies,
                    normalized_input=normalized_input,
                    detached_history=detached_history,
                )
            except Exception as cause:
                error = AgentAdmissionError(
                    "Junjo could not prepare the validated Agent invocation for admission.",
                    agent_key=agent.key,
                    definition_id=agent.definition_id,
                    structural_id=agent.structural_id,
                    run_id=run_id,
                )
                error.__cause__ = cause
                _record_invocation_failure(span, error)
                outcome = _ExecutionOutcome(error=error)
            else:
                outcome = await _execute_admitted(agent=agent, admitted=admitted, span=span)
    return _propagate_outcome(outcome)


def _validate_invocation(
    *,
    agent: Agent,
    run_id: str,
    span: Span,
    input: object,
    history: Sequence[AgentMessage],
) -> tuple[JsonValue, tuple[AgentMessage, ...]]:
    try:
        _typed_input, frozen_input = validate_and_detach(agent.input_adapter, input)
        normalized_input = thaw_json(frozen_input)
        _require_agent_state_message_capacity(AgentInputMessage(normalized_input))
    except Exception as exc:
        evidence = record_candidate(
            span,
            availability_root="junjo.agent.input_candidate.available",
            payload_root="junjo.agent.input_candidate",
            candidate=input,
        )
        raise AgentInputValidationError(
            "Agent input failed declared validation.",
            agent_key=agent.key,
            definition_id=agent.definition_id,
            structural_id=agent.structural_id,
            run_id=run_id,
            evidence=evidence,
        ) from exc
    try:
        detached_history = validate_history(history)
        freeze_json({"history": [message_to_json(message) for message in detached_history]})
    except Exception as exc:
        evidence = record_candidate(
            span,
            availability_root="junjo.agent.history_candidate.available",
            payload_root="junjo.agent.history_candidate",
            candidate=_history_candidate(history),
        )
        raise AgentHistoryValidationError(
            "Agent history is not a sequence of complete normalized exchanges.",
            agent_key=agent.key,
            definition_id=agent.definition_id,
            structural_id=agent.structural_id,
            run_id=run_id,
            evidence=evidence,
        ) from exc
    return normalized_input, detached_history


def _require_agent_state_message_capacity(message: AgentMessage) -> None:
    """Prove one message fits its deepest complete Agent-State payload slot."""

    freeze_json({"transcript": [message_to_json(message)]})


def _admit_run(
    *,
    agent: Agent[InputT, OutputT, DependenciesT],
    run_id: str,
    parent: ParentExecutableIdentity | None,
    span: Span,
    dependencies: DependenciesT,
    normalized_input: JsonValue,
    detached_history: tuple[AgentMessage, ...],
) -> _AdmittedRun[InputT, OutputT, DependenciesT]:
    current_input = AgentInputMessage(normalized_input)
    transcript = (*detached_history, current_input)
    initial_state = initial_agent_state(
        normalized_input=normalized_input,
        history=[_message_json_value(message) for message in detached_history],
        transcript=[_message_json_value(current_input)],
    )
    store = AgentStore(initial_state)
    initial_evidence = store._get_initial_store_owner_evidence()
    dispatcher = LifecycleDispatcher(agent.hooks)
    runtime = _AgentRun(
        agent=agent,
        run_id=run_id,
        dependencies=dependencies,
        transcript=transcript,
        store=store,
        dispatcher=dispatcher,
        initial_state=initial_state,
    )

    # Publish subordinate Store facts only after the complete admission package
    # has been prepared.  Availability is the final publication boundary.
    span.set_attribute("junjo.agent.store.id", store.id)
    set_full_payload(span, "junjo.agent.input", normalized_input)
    set_full_payload(span, "junjo.agent.state.start", initial_evidence.state_start)
    span.set_attribute("junjo.store.revision.start", initial_evidence.revision_start)
    span.set_attribute("junjo.agent.state.available", True)
    return _AdmittedRun(
        runtime=runtime,
        lifecycle_identity=_lifecycle_identity(
            agent=agent,
            run_id=run_id,
            store_id=store.id,
            span=span,
            parent=parent,
        ),
        active_identity=ActiveExecutableIdentity(
            executable_definition_id=agent.definition_id,
            executable_name=agent.name,
            executable_type=ExecutableType.AGENT,
            executable_runtime_id=run_id,
            executable_structural_id=agent.structural_id,
        ),
    )


async def _execute_admitted(
    *,
    agent: Agent[InputT, OutputT, DependenciesT],
    admitted: _AdmittedRun[InputT, OutputT, DependenciesT],
    span: Span,
) -> _ExecutionOutcome[OutputT]:
    runtime = admitted.runtime
    with active_executable_identity(admitted.active_identity):
        try:
            await runtime.dispatcher.agent_started(admitted.lifecycle_identity)
            completion = await runtime.run()
        except asyncio.CancelledError as cancellation:
            selected_outcome = "cancelled"
            selected_error = None
            selected_cancellation = cancellation
        except AgentExecutionError as error:
            selected_outcome = "failed"
            selected_error = error
            selected_cancellation = None
        except Exception as cause:
            error = AgentInternalError(
                "Unexpected error inside the admitted Agent runtime.",
                agent_key=agent.key,
                definition_id=agent.definition_id,
                structural_id=agent.structural_id,
                run_id=runtime.run_id,
                state=snapshot_agent_state(runtime._get_last_known_state()),
            )
            error.__cause__ = cause
            selected_outcome = "failed"
            selected_error = error
            selected_cancellation = None
        else:
            selected_outcome = "completed"
            selected_error = None
            selected_cancellation = None

        # This is the single outer boundary for the selected terminal
        # transaction.  No failure in admitted terminal machinery is allowed
        # to leak as an untyped implementation exception.
        try:
            if selected_outcome == "completed":
                return await _finish_success(
                    agent=agent,
                    admitted=admitted,
                    span=span,
                    completion=completion,
                )
            if selected_outcome == "cancelled":
                assert selected_cancellation is not None
                return await _finish_cancellation(admitted, span, selected_cancellation)
            assert selected_error is not None
            return await _finish_failure(admitted, span, selected_error)
        except (asyncio.CancelledError, Exception) as terminal_failure:
            return await _finish_terminal_commit_failure(
                admitted=admitted,
                span=span,
                selected_outcome=selected_outcome,
                selected_error=selected_error,
                selected_cancellation=selected_cancellation,
                cause=terminal_failure,
            )


async def _finish_success(
    *,
    agent: Agent[InputT, OutputT, DependenciesT],
    admitted: _AdmittedRun[InputT, OutputT, DependenciesT],
    span: Span,
    completion: _PreparedCompletion[OutputT],
) -> _ExecutionOutcome[OutputT]:
    runtime = admitted.runtime
    result, finalization_cancellation = await drain_terminal_work(
        _commit_success_terminal(
            agent=agent,
            runtime=runtime,
            span=span,
            completion=completion,
        )
    )
    try:
        await _dispatch_terminal(
            runtime.dispatcher,
            runtime.dispatcher.agent_completed(
                identity=admitted.lifecycle_identity,
                result=_clone_result(agent, result),
            ),
        )
    except asyncio.CancelledError as cancellation:
        return _ExecutionOutcome(
            result=result,
            terminal_delivery_cancellation=cancellation,
        )
    except Exception as observer_failure:
        _record_terminal_dispatch_failure(span, observer_failure)
    return _ExecutionOutcome(
        result=result,
        terminal_delivery_cancellation=finalization_cancellation,
    )


async def _finish_failure(
    admitted: _AdmittedRun,
    span: Span,
    error: AgentExecutionError,
) -> _ExecutionOutcome:
    runtime = admitted.runtime
    state, finalization_cancellation = await drain_terminal_work(
        _commit_failure_terminal(runtime=runtime, span=span, error=error)
    )
    try:
        await _dispatch_terminal(
            runtime.dispatcher,
            runtime.dispatcher.agent_failed(
                identity=admitted.lifecycle_identity,
                error=_clone_execution_error(error),
                state=snapshot_agent_state(state),
            ),
        )
    except asyncio.CancelledError as cancellation:
        return _ExecutionOutcome(
            error=error,
            terminal_delivery_cancellation=cancellation,
        )
    except Exception as observer_failure:
        _record_terminal_dispatch_failure(span, observer_failure)
    return _ExecutionOutcome(
        error=error,
        terminal_delivery_cancellation=finalization_cancellation,
    )


async def _finish_cancellation(
    admitted: _AdmittedRun,
    span: Span,
    cancellation: asyncio.CancelledError,
) -> _ExecutionOutcome:
    runtime = admitted.runtime
    state, finalization_cancellation = await drain_terminal_work(
        _commit_cancellation_terminal(
            runtime=runtime,
            span=span,
            cancellation=cancellation,
        )
    )
    try:
        await _dispatch_terminal(
            runtime.dispatcher,
            runtime.dispatcher.agent_cancelled(
                identity=admitted.lifecycle_identity,
                reason=_cancellation_reason(cancellation),
                state=snapshot_agent_state(state),
            ),
        )
    except asyncio.CancelledError as delivery_cancellation:
        return _ExecutionOutcome(
            cancellation=cancellation,
            terminal_delivery_cancellation=delivery_cancellation,
        )
    except Exception as observer_failure:
        _record_terminal_dispatch_failure(span, observer_failure)
    return _ExecutionOutcome(
        cancellation=cancellation,
        terminal_delivery_cancellation=finalization_cancellation,
    )


async def _finish_terminal_commit_failure(
    *,
    admitted: _AdmittedRun,
    span: Span,
    selected_outcome: str,
    selected_error: AgentExecutionError | None,
    selected_cancellation: asyncio.CancelledError | None,
    cause: BaseException,
) -> _ExecutionOutcome:
    """Supersede a broken terminal transaction with one typed internal outcome."""

    runtime = admitted.runtime
    try:
        (error, state), finalization_cancellation = await drain_terminal_work(
            _commit_internal_failure_terminal(
                runtime=runtime,
                span=span,
                selected_outcome=selected_outcome,
                selected_error=selected_error,
                selected_cancellation=selected_cancellation,
                cause=cause,
            )
        )
    except (asyncio.CancelledError, Exception) as recovery_failure:
        # Emergency recording itself is best effort.  The public boundary still
        # returns a typed error built from the last detached state known before
        # any further await, never the raw recovery failure.
        error = _new_internal_error(
            runtime,
            "Junjo could not complete Agent terminal recovery.",
            recovery_failure,
        )
        error.superseded_outcome = selected_outcome
        error.superseded_error = selected_error
        error.superseded_cancellation = selected_cancellation
        state = runtime._get_last_known_state()
        error.state = snapshot_agent_state(state)
        error.evidence = error.state
        _record_minimal_internal_owner(span, runtime, error, state)
        finalization_cancellation = None

    delivery_cancellation: asyncio.CancelledError | None = None
    try:
        await _dispatch_terminal(
            runtime.dispatcher,
            runtime.dispatcher.agent_failed(
                identity=admitted.lifecycle_identity,
                error=_clone_execution_error(error),
                state=snapshot_agent_state(state),
            ),
        )
    except asyncio.CancelledError as cancellation:
        delivery_cancellation = cancellation
    except Exception as observer_failure:
        _record_terminal_dispatch_failure(span, observer_failure)

    return _ExecutionOutcome(
        error=error,
        terminal_delivery_cancellation=(delivery_cancellation or finalization_cancellation),
    )


async def _commit_internal_failure_terminal(
    *,
    runtime: _AgentRun,
    span: Span,
    selected_outcome: str,
    selected_error: AgentExecutionError | None,
    selected_cancellation: asyncio.CancelledError | None,
    cause: BaseException,
) -> tuple[AgentInternalError, AgentState]:
    """Record truthful best-effort evidence after terminal machinery fails."""

    error = _new_internal_error(
        runtime,
        "Unexpected error while committing the selected Agent outcome.",
        cause,
    )
    error.superseded_outcome = selected_outcome
    error.superseded_error = selected_error
    error.superseded_cancellation = selected_cancellation

    try:
        await runtime.store.set_terminal_reason("internal_error")
    except (asyncio.CancelledError, Exception):
        pass

    state = runtime._get_last_known_state()
    try:
        state = await runtime._get_state()
    except (asyncio.CancelledError, Exception):
        pass
    error.state = snapshot_agent_state(state)
    error.evidence = error.state

    _record_minimal_internal_owner(span, runtime, error, state)

    try:
        evidence = await runtime.store._get_store_owner_evidence()
    except (asyncio.CancelledError, Exception):
        evidence = None
    if evidence is not None:
        try:
            set_full_payload(span, "junjo.agent.state.end", evidence.state_end)
            span.set_attribute("junjo.store.revision.end", evidence.revision_end)
            span.set_attribute(
                "junjo.store.transition.count",
                evidence.transition_count,
            )
        except Exception:
            pass

    # A failed terminal transaction is intentionally partial even when a
    # post-failure Store snapshot can be read and replayed.
    try:
        span.set_attribute("junjo.store.reconstructable", False)
    except Exception:
        pass
    return error, state


def _new_internal_error(
    runtime: _AgentRun,
    message: str,
    cause: BaseException,
) -> AgentInternalError:
    error = AgentInternalError(
        message,
        **runtime._error_identity(),
        state=snapshot_agent_state(runtime._get_last_known_state()),
    )
    error.__cause__ = cause
    return error


def _record_minimal_internal_owner(
    span: Span,
    runtime: _AgentRun,
    error: AgentInternalError,
    state: AgentState,
) -> None:
    """Set only locally known owner facts; every telemetry call is best effort."""

    try:
        cause = error.__cause__
        superseded_outcome = error.superseded_outcome or "unknown"
        finalize_agent_counts(
            span,
            operation_count=runtime.operation_count,
            model_request_count=state.model_request_count,
            tool_call_requested_count=state.tool_call_requested_count,
            tool_call_admitted_count=state.tool_call_admitted_count,
            tool_call_started_count=state.tool_call_started_count,
            tool_call_completed_count=state.tool_call_completed_count,
            usage=runtime.usage,
        )
        span.set_attribute("junjo.agent.outcome", "failed")
        span.set_attribute("junjo.agent.termination_reason", "internal_error")
        span.set_attribute("junjo.store.reconstructable", False)
        span.add_event(
            "junjo.agent.terminal_commit_failed",
            attributes={
                "error.type": error_type(cause if cause is not None else error),
                "junjo.agent.superseded_outcome": superseded_outcome,
            },
        )
        mark_span_failed(span, error)
        record_span_exception(span, error)
    except Exception:
        pass


def _record_terminal_dispatch_failure(span: Span, failure: Exception) -> None:
    """Keep a committed execution outcome when terminal observer setup fails."""

    try:
        span.add_event(
            "junjo.hook_error",
            attributes={
                "junjo.hook.event": "terminal_dispatch",
                "junjo.hook.callback": "junjo.lifecycle.dispatcher",
                "junjo.hook.error.type": error_type(failure),
                "junjo.hook.error.message": exception_message(failure),
            },
        )
    except Exception:
        pass


async def _commit_success_terminal(
    *,
    agent: Agent[InputT, OutputT, DependenciesT],
    runtime: _AgentRun[InputT, OutputT, DependenciesT],
    span: Span,
    completion: _PreparedCompletion[OutputT],
) -> AgentExecutionResult[OutputT]:
    await runtime.store.commit_success(completion.normalized_output)
    state = await runtime._get_state()
    transcript = (
        *runtime.transcript,
        AssistantOutputMessage(completion.normalized_output),
    )
    result = _build_result(
        agent,
        runtime,
        state,
        completion.typed_output,
        transcript,
    )
    await _set_terminal_agent_telemetry(
        span,
        store=runtime.store,
        state=state,
        operation_count=runtime.operation_count,
        usage=runtime.usage,
        outcome="completed",
        reason="final_output",
    )
    set_full_payload(span, "junjo.agent.output", state.final_output)
    return result


async def _commit_failure_terminal(
    *,
    runtime: _AgentRun,
    span: Span,
    error: AgentExecutionError,
) -> AgentState:
    await runtime.store.set_terminal_reason(error.termination_reason)
    state = await runtime._get_state()
    error.state = snapshot_agent_state(state)
    error.evidence = error.state
    await _set_terminal_agent_telemetry(
        span,
        store=runtime.store,
        state=state,
        operation_count=runtime.operation_count,
        usage=runtime.usage,
        outcome="failed",
        reason=error.termination_reason,
    )
    _set_limit_evidence(span, error)
    mark_span_failed(span, error)
    record_span_exception(span, error)
    return state


async def _commit_cancellation_terminal(
    *,
    runtime: _AgentRun,
    span: Span,
    cancellation: asyncio.CancelledError,
) -> AgentState:
    await runtime.store.set_terminal_reason("cancelled")
    state = await runtime._get_state()
    await _set_terminal_agent_telemetry(
        span,
        store=runtime.store,
        state=state,
        operation_count=runtime.operation_count,
        usage=runtime.usage,
        outcome="cancelled",
        reason="cancelled",
    )
    mark_span_cancelled(span, cancellation)
    return state


def _record_invocation_failure(span: Span, error: AgentInvocationError) -> None:
    finalize_agent_counts(
        span,
        operation_count=0,
        model_request_count=0,
        tool_call_requested_count=0,
        tool_call_admitted_count=0,
        tool_call_started_count=0,
        tool_call_completed_count=0,
        usage=AgentUsage(),
    )
    span.set_attribute("junjo.agent.outcome", "failed")
    span.set_attribute("junjo.agent.termination_reason", error.termination_reason)
    mark_span_failed(span, error)
    record_span_exception(span, error)


def _propagate_outcome(
    outcome: _ExecutionOutcome[OutputT],
) -> AgentExecutionResult[OutputT]:
    if outcome.terminal_delivery_cancellation is not None:
        raise outcome.terminal_delivery_cancellation
    if outcome.cancellation is not None:
        raise outcome.cancellation
    if outcome.error is not None:
        raise outcome.error
    assert outcome.result is not None
    return outcome.result


def _build_result(
    agent: Agent[InputT, OutputT, DependenciesT],
    runtime: _AgentRun[InputT, OutputT, DependenciesT],
    state: AgentState,
    output: OutputT,
    transcript: tuple[AgentMessage, ...],
) -> AgentExecutionResult[OutputT]:
    return AgentExecutionResult(
        agent_key=agent.key,
        name=agent.name,
        definition_id=agent.definition_id,
        structural_id=agent.structural_id,
        run_id=runtime.run_id,
        output=output,
        transcript=transcript,
        usage=runtime.usage,
        model_request_count=state.model_request_count,
        tool_call_requested_count=state.tool_call_requested_count,
        tool_call_admitted_count=state.tool_call_admitted_count,
        tool_call_started_count=state.tool_call_started_count,
        tool_call_completed_count=state.tool_call_completed_count,
    )


def _clone_result(
    agent: Agent[InputT, OutputT, DependenciesT],
    result: AgentExecutionResult[OutputT],
) -> AgentExecutionResult[OutputT]:
    cloned_output, _normalized = validate_and_detach(agent.output_adapter, result.output)
    return AgentExecutionResult(
        agent_key=result.agent_key,
        name=result.name,
        definition_id=result.definition_id,
        structural_id=result.structural_id,
        run_id=result.run_id,
        output=cast(OutputT, cloned_output),
        transcript=result.transcript,
        usage=result.usage,
        model_request_count=result.model_request_count,
        tool_call_requested_count=result.tool_call_requested_count,
        tool_call_admitted_count=result.tool_call_admitted_count,
        tool_call_started_count=result.tool_call_started_count,
        tool_call_completed_count=result.tool_call_completed_count,
    )


def _clone_execution_error(error: AgentExecutionError) -> AgentExecutionError:
    state = error.state
    kwargs: dict[str, object] = {
        "agent_key": error.agent_key,
        "definition_id": error.definition_id,
        "structural_id": error.structural_id,
        "run_id": error.run_id,
        "state": state,
    }
    if isinstance(error, AgentLimitExceededError):
        kwargs.update(
            limit_kind=error.limit_kind,
            limit=error.limit,
            attempted_count=error.attempted_count,
            requested_batch_size=error.requested_batch_size,
        )
    if isinstance(
        error,
        (
            AgentUnknownToolError,
            AgentToolInputValidationError,
            AgentToolError,
            AgentToolOutputValidationError,
        ),
    ):
        kwargs.update(
            tool_name=error.tool_name,
            tool_call_id=error.tool_call_id,
            call_ordinal=error.call_ordinal,
        )
    clone = type(error)(exception_message(error), **kwargs)
    clone.__cause__ = error.__cause__
    if isinstance(error, AgentInternalError):
        internal_clone = cast(AgentInternalError, clone)
        internal_clone.superseded_outcome = error.superseded_outcome
        internal_clone.superseded_error = error.superseded_error
        internal_clone.superseded_cancellation = error.superseded_cancellation
    return clone


async def _dispatch_terminal(
    dispatcher: LifecycleDispatcher,
    event: PreparedHookEvent | None,
) -> None:
    await dispatcher.dispatch(event, terminal=True)


def _history_candidate(history: Sequence[AgentMessage]) -> object:
    try:
        return [message_to_json(message) for message in history]
    except Exception:
        return history


def _message_json_value(message: AgentMessage) -> JsonValue:
    return thaw_json(freeze_json(message_to_json(message)))


def _lifecycle_identity(
    *,
    agent: Agent,
    run_id: str,
    store_id: str,
    span: Span,
    parent: ParentExecutableIdentity | None,
) -> AgentLifecycleIdentity:
    trace_id, span_id = get_span_identifiers(span)
    return AgentLifecycleIdentity(
        run_id=run_id,
        executable_definition_id=agent.definition_id,
        name=agent.name,
        agent_key=agent.key,
        store_id=store_id,
        trace_id=trace_id,
        span_id=span_id,
        executable_structural_id=agent.structural_id,
        parent_executable_definition_id=(parent.executable_definition_id if parent is not None else None),
        parent_executable_runtime_id=(parent.executable_runtime_id if parent is not None else None),
        parent_executable_structural_id=(parent.executable_structural_id if parent is not None else None),
        parent_executable_type=parent.executable_type if parent is not None else None,
    )


async def _set_terminal_agent_telemetry(
    span: Span,
    *,
    store: AgentStore,
    state: AgentState,
    operation_count: int,
    usage: AgentUsage,
    outcome: str,
    reason: str,
) -> None:
    finalize_agent_counts(
        span,
        operation_count=operation_count,
        model_request_count=state.model_request_count,
        tool_call_requested_count=state.tool_call_requested_count,
        tool_call_admitted_count=state.tool_call_admitted_count,
        tool_call_started_count=state.tool_call_started_count,
        tool_call_completed_count=state.tool_call_completed_count,
        usage=usage,
    )
    span.set_attribute("junjo.agent.outcome", outcome)
    span.set_attribute("junjo.agent.termination_reason", reason)
    evidence = await store._get_store_owner_evidence()
    set_full_payload(span, "junjo.agent.state.end", evidence.state_end)
    span.set_attribute("junjo.store.revision.end", evidence.revision_end)
    span.set_attribute("junjo.store.transition.count", evidence.transition_count)
    span.set_attribute("junjo.store.reconstructable", evidence.reconstructable)


def _set_limit_evidence(span: Span, error: AgentExecutionError) -> None:
    if not isinstance(error, AgentLimitExceededError):
        return
    span.set_attribute("junjo.agent.limit.exceeded", error.limit_kind)
    span.set_attribute("junjo.agent.limit.attempted_count", error.attempted_count)
    if error.requested_batch_size is not None:
        span.set_attribute(
            "junjo.agent.limit.requested_batch_size",
            error.requested_batch_size,
        )


def _cancellation_reason(exc: asyncio.CancelledError) -> str:
    return cancellation_reason(exc)


@contextmanager
def _operation_cancellation(
    span: Span,
    *,
    availability_root: str,
    evidence_recorded: list[bool],
):
    """Make cancellation truthful across every await in an operation span."""

    try:
        yield
    except asyncio.CancelledError as exc:
        if not evidence_recorded[0]:
            record_unavailable(
                span,
                availability_root=availability_root,
                reason="cancelled",
            )
            evidence_recorded[0] = True
        mark_span_cancelled(span, exc)
        raise
    except Exception as exc:
        if not isinstance(exc, AgentExecutionError):
            mark_span_failed(span, exc)
            record_span_exception(span, exc)
        raise
