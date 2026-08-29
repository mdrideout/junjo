"""AI Chat declarations consumed by Junjo's SDK-owned evaluation harness."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from junjo import ExecutionCorrelation
from junjo.evaluation import (
    AgentInvocation,
    AgentTarget,
    CallbackEvaluator,
    EvaluationContext,
    EvaluationHarness,
    EvaluationResult,
    ExecutionServiceIdentity,
    NodeInvocation,
    NodeTarget,
    WorkflowInvocation,
    WorkflowTarget,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_chat.application.chat_agent import create_chat_agent
from ai_chat.application.chat_agent.definition import CHAT_AGENT_NAME
from ai_chat.application.dependencies import ChatDependencies
from ai_chat.application.turn_workflow.factory import TURN_WORKFLOW_NAME, create_turn_workflow
from ai_chat.application.turn_workflow.nodes import CreateDateIdeaResponseNode
from ai_chat.application.turn_workflow.state import TurnWorkflowState, TurnWorkflowStore
from ai_chat.bootstrap import (
    ChatApplication,
    ProviderRuntime,
    build_application,
    build_provider_runtime,
)
from ai_chat.config import APPLICATION_SERVICE_SCOPE, Settings
from ai_chat.domain.models import (
    ChatAgentInput,
    ChatMessage,
    ContextPolicyReference,
    ImageArtifact,
    MessageRole,
    Turn,
    TurnStatus,
)
from ai_chat.evals.fixtures import create_fixed_contact, fixed_contact_profile
from ai_chat.evals.judges import judge_local_place_text, judge_text
from ai_chat.evals.local_places import VERIFIED_PLACES_BY_ID, verify_local_place_claims
from ai_chat.telemetry import TelemetryRuntime, start_telemetry

APPLICATION_KEY = "ai_chat"
DATE_RESPONSE_NODE_TARGET = "turn.date_response"
TURN_WORKFLOW_TARGET = "turn"
CHAT_AGENT_TARGET = "chat"
LOCAL_PLACE_INPUT_VERSION = 1
TEXT_QUALITY_EVALUATOR = "text.quality"
TEXT_QUALITY_EVALUATOR_VERSION = 1
LOCAL_PLACE_QUALITY_EVALUATOR = "local_place.quality"
LOCAL_PLACE_QUALITY_EVALUATOR_VERSION = 1


class LocalPlaceInputV1(BaseModel):
    """Version-one input shared by focused and end-to-end local-place cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=2_500)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Local-place message cannot be blank.")
        return normalized


class TextQualityExpectationV1(BaseModel):
    """One explicit natural-language rubric for the AI Chat quality judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rubric: str = Field(min_length=1, max_length=8_000)

    @field_validator("rubric")
    @classmethod
    def normalize_rubric(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Text-quality rubric cannot be blank.")
        return normalized


class LocalPlaceQualityExpectationV1(BaseModel):
    """Qualitative rubric plus explicit current-place facts for one Case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rubric: str = Field(min_length=1, max_length=8_000)
    verified_place_ids: tuple[str, ...] = Field(min_length=1)
    minimum_verified_places: int = Field(default=1, ge=1)

    @field_validator("rubric")
    @classmethod
    def normalize_rubric(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Local-place quality rubric cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_verified_places(self) -> LocalPlaceQualityExpectationV1:
        if len(set(self.verified_place_ids)) != len(self.verified_place_ids):
            raise ValueError("Verified place IDs must be unique.")
        unknown_ids = set(self.verified_place_ids).difference(VERIFIED_PLACES_BY_ID)
        if unknown_ids:
            unknown = ", ".join(sorted(unknown_ids))
            raise ValueError(f"Unknown verified place IDs: {unknown}.")
        if self.minimum_verified_places > len(self.verified_place_ids):
            raise ValueError("Minimum verified places cannot exceed the verified place count.")
        return self


@dataclass(frozen=True, slots=True)
class EvaluationRuntime:
    """One application host runtime reused for an executor lifetime."""

    settings: Settings
    provider: ProviderRuntime
    telemetry: TelemetryRuntime


@dataclass(slots=True)
class _CaseApplication:
    application: ChatApplication
    workspace: TemporaryDirectory

    async def close(self) -> None:
        errors: list[BaseException] = []
        try:
            await self.application.close()
        except BaseException as error:
            errors.append(error)
        try:
            self.workspace.cleanup()
        except BaseException as error:
            errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("AI Chat evaluation case cleanup failed", errors)


def authored_local_place_input(message: str) -> dict[str, object]:
    """Build version-one JSON for any registered local-place target."""

    return LocalPlaceInputV1(message=message).model_dump(mode="json")


def text_quality_expectation(rubric: str) -> dict[str, object]:
    """Build the explicit version-one text-quality expectation."""

    return TextQualityExpectationV1(rubric=rubric).model_dump(mode="json")


def local_place_quality_expectation(
    rubric: str,
    *,
    verified_place_ids: tuple[str, ...],
    minimum_verified_places: int = 1,
) -> dict[str, object]:
    """Build the version-one local-place quality expectation."""

    return LocalPlaceQualityExpectationV1(
        rubric=rubric,
        verified_place_ids=verified_place_ids,
        minimum_verified_places=minimum_verified_places,
    ).model_dump(mode="json")


async def _date_node_factory(
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> NodeInvocation[TurnWorkflowState]:
    now = datetime.now(UTC)
    contact = fixed_contact_profile(avatar=_fixed_avatar())
    return NodeInvocation(
        node=CreateDateIdeaResponseNode(resources.provider.language),
        store=TurnWorkflowStore(
            initial_state=TurnWorkflowState(
                turn=_focused_turn(input_value.message, now=now),
                contact=contact,
            )
        ),
        correlation=_correlation(context),
    )


def _date_node_projector(
    result,
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> str:
    del context, resources
    contact = result.state.contact
    response = result.state.response
    if contact is None or response is None:
        raise RuntimeError("Focused date-response Node produced no response.")
    return _text_subject(
        profile_json=contact.model_dump_json(indent=2),
        message=input_value.message,
        response=response.message,
    )


async def _turn_workflow_factory(
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> WorkflowInvocation:
    case = await _new_case_application(resources)
    try:
        overview = await create_fixed_contact(
            case.application,
            with_local_avatar=False,
        )
        turn = await case.application.store.admit_turn(
            conversation_id=overview.conversation.id,
            turn_id="eval-turn",
            text=input_value.message,
            context_policy=ContextPolicyReference(),
        )
        turn = await case.application.store.start_turn(turn.id)
        workflow = create_turn_workflow(
            turn=turn,
            agent=case.application.turns.agent,
            turns=case.application.store,
            history=case.application.store,
            contacts=case.application.store,
            language=resources.provider.language,
            images=case.application.images,
        )
        return WorkflowInvocation(
            workflow=workflow,
            correlation=_correlation(context),
            cleanup=case.close,
        )
    except BaseException:
        await case.close()
        raise


def _turn_workflow_projector(
    result,
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> str:
    del context, resources
    contact = result.state.contact
    response = result.state.response
    if contact is None or response is None:
        raise RuntimeError("Turn Workflow produced no assistant response.")
    return _text_subject(
        profile_json=contact.model_dump_json(indent=2),
        message=input_value.message,
        response=response.message,
    )


async def _chat_agent_factory(
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> AgentInvocation:
    case = await _new_case_application(resources)
    try:
        overview = await create_fixed_contact(
            case.application,
            with_local_avatar=False,
        )
        turn_id = "eval-agent-turn"
        dependencies = ChatDependencies(
            conversation_id=overview.conversation.id,
            turn_id=turn_id,
            before_sequence=1,
            contact=overview.contact,
            recent_turns=(),
            history=case.application.store,
            language=resources.provider.language,
            images=case.application.images,
        )
        return AgentInvocation(
            agent=create_chat_agent(resources.provider.model),
            input=ChatAgentInput(
                conversation_id=overview.conversation.id,
                turn_id=turn_id,
                contact=overview.contact,
                message=input_value.message,
            ),
            dependencies=dependencies,
            correlation=_correlation(context),
            cleanup=case.close,
        )
    except BaseException:
        await case.close()
        raise


def _chat_agent_projector(
    result,
    input_value: LocalPlaceInputV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> str:
    del context, resources
    return _text_subject(
        profile_json=fixed_contact_profile(avatar=_fixed_avatar()).model_dump_json(indent=2),
        message=input_value.message,
        response=result.output.message,
    )


async def _text_quality_callback(
    subject: object,
    expectation: TextQualityExpectationV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> EvaluationResult:
    del context
    if not isinstance(subject, str):
        raise TypeError("AI Chat text-quality evaluation requires a string subject.")
    judgment = await judge_text(
        language=resources.provider.language,
        rubric=expectation.rubric,
        subject=subject,
    )
    return EvaluationResult(
        passed=judgment.passed,
        reason=judgment.reason,
    )


async def _local_place_quality_callback(
    subject: object,
    expectation: LocalPlaceQualityExpectationV1,
    context: EvaluationContext,
    resources: EvaluationRuntime,
) -> EvaluationResult:
    del context
    if not isinstance(subject, str):
        raise TypeError("AI Chat local-place evaluation requires a string subject.")
    _assistant_response(subject)
    judgment = await judge_local_place_text(
        language=resources.provider.language,
        rubric=expectation.rubric,
        subject=subject,
    )
    factual = verify_local_place_claims(
        judgment.places,
        verified_place_ids=expectation.verified_place_ids,
        minimum_verified_places=expectation.minimum_verified_places,
    )
    if not factual.passed:
        return EvaluationResult(passed=False, reason=factual.reason)

    if not judgment.passed:
        return EvaluationResult(
            passed=False,
            reason=f"{factual.reason} Qualitative check failed: {judgment.reason}",
        )
    return EvaluationResult(
        passed=True,
        reason=f"{factual.reason} Qualitative check passed: {judgment.reason}",
    )


@asynccontextmanager
async def evaluation_runtime() -> AsyncIterator[EvaluationRuntime]:
    """Run the same provider and telemetry lifetime as an application host."""

    settings = Settings.from_environment()
    if settings.telemetry is None:
        raise ValueError("JUNJO_AI_STUDIO_API_KEY is required for evaluation execution telemetry.")
    telemetry = start_telemetry(
        settings.telemetry,
        service_scope=APPLICATION_SERVICE_SCOPE,
    )
    provider: ProviderRuntime | None = None
    selected_error: BaseException | None = None
    try:
        provider = build_provider_runtime(settings)
        yield EvaluationRuntime(
            settings=settings,
            provider=provider,
            telemetry=telemetry,
        )
    except BaseException as error:
        selected_error = error

    cleanup_errors: list[BaseException] = []
    if provider is not None:
        try:
            await provider.close()
        except BaseException as error:
            cleanup_errors.append(error)
    try:
        telemetry.shutdown()
    except BaseException as error:
        cleanup_errors.append(error)

    if selected_error is not None:
        if cleanup_errors:
            raise BaseExceptionGroup(
                "AI Chat evaluation and cleanup failed",
                [selected_error, *cleanup_errors],
            )
        raise selected_error
    if len(cleanup_errors) == 1:
        raise cleanup_errors[0]
    if cleanup_errors:
        raise BaseExceptionGroup("AI Chat evaluation cleanup failed", cleanup_errors)


async def _new_case_application(
    resources: EvaluationRuntime,
) -> _CaseApplication:
    workspace = TemporaryDirectory(prefix="ai-chat-eval-")
    directory = Path(workspace.name)
    settings = replace(
        resources.settings,
        database_path=directory / "chat.sqlite3",
        image_directory=directory / "images",
    )
    application = build_application(
        settings,
        model=resources.provider.model,
        language=resources.provider.language,
        images=resources.provider.images_for_directory(settings.image_directory),
    )
    case = _CaseApplication(application=application, workspace=workspace)
    try:
        await application.initialize()
    except BaseException:
        await case.close()
        raise
    return case


def _correlation(context: EvaluationContext) -> ExecutionCorrelation:
    identity = context.attempt_id or f"{context.dataset_id}:{context.case_key}"
    return ExecutionCorrelation(type="ai_chat.evaluation", id=identity)


def _focused_turn(message: str, *, now: datetime) -> Turn:
    return Turn(
        id="eval-focused-turn",
        revision=1,
        conversation_id="eval-conversation",
        sequence=1,
        status=TurnStatus.RUNNING,
        context_policy=ContextPolicyReference(),
        user_message=ChatMessage(
            id="eval-focused-message",
            turn_id="eval-focused-turn",
            conversation_id="eval-conversation",
            role=MessageRole.USER,
            content=message,
            created_at=now,
        ),
        created_at=now,
        updated_at=now,
    )


def _fixed_avatar() -> ImageArtifact:
    return ImageArtifact(
        id="eval-avatar",
        url="/api/images/eval-avatar.png",
        alt_text="Portrait of Maya Chen",
    )


def _text_subject(*, profile_json: str, message: str, response: str) -> str:
    return f"PROFILE:\n{profile_json}\n\nCURRENT USER MESSAGE:\n{message}\n\nASSISTANT RESPONSE:\n{response}"


def _assistant_response(subject: str) -> str:
    marker = "\n\nASSISTANT RESPONSE:\n"
    _, separator, response = subject.partition(marker)
    if not separator or not response.strip():
        raise ValueError("AI Chat local-place subject has no assistant response.")
    return response.strip()


harness = EvaluationHarness(
    application_key=APPLICATION_KEY,
    service_identity=ExecutionServiceIdentity(
        service_namespace=APPLICATION_SERVICE_SCOPE.namespace,
        service_name=APPLICATION_SERVICE_SCOPE.name,
    ),
    targets=(
        NodeTarget(
            key=DATE_RESPONSE_NODE_TARGET,
            name=CreateDateIdeaResponseNode.__name__,
            input_version=LOCAL_PLACE_INPUT_VERSION,
            input_type=LocalPlaceInputV1,
            factory=_date_node_factory,
            projector=_date_node_projector,
        ),
        WorkflowTarget(
            key=TURN_WORKFLOW_TARGET,
            name=TURN_WORKFLOW_NAME,
            input_version=LOCAL_PLACE_INPUT_VERSION,
            input_type=LocalPlaceInputV1,
            factory=_turn_workflow_factory,
            projector=_turn_workflow_projector,
        ),
        AgentTarget(
            key=CHAT_AGENT_TARGET,
            name=CHAT_AGENT_NAME,
            input_version=LOCAL_PLACE_INPUT_VERSION,
            input_type=LocalPlaceInputV1,
            factory=_chat_agent_factory,
            projector=_chat_agent_projector,
        ),
    ),
    evaluators=(
        CallbackEvaluator(
            key=TEXT_QUALITY_EVALUATOR,
            version=TEXT_QUALITY_EVALUATOR_VERSION,
            expectation_type=TextQualityExpectationV1,
            callback=_text_quality_callback,
        ),
        CallbackEvaluator(
            key=LOCAL_PLACE_QUALITY_EVALUATOR,
            version=LOCAL_PLACE_QUALITY_EVALUATOR_VERSION,
            expectation_type=LocalPlaceQualityExpectationV1,
            callback=_local_place_quality_callback,
        ),
    ),
    runtime_context=evaluation_runtime,
)
