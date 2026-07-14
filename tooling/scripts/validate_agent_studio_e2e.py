#!/usr/bin/env python3
"""Prove the live SDK -> OTLP -> Studio Agent diagnostic path end to end.

This validator is intentionally provider-free. It executes a deterministic
public Junjo ``Agent -> Tool -> Workflow -> Nodes`` composition with
``ScriptedModelDriver``, exports the real spans to a running local Studio, and
then validates both Studio's raw transport view and its semantic Agent and
Workflow Store APIs.

The target Studio must be a disposable local development instance. When its
user database is empty, the validator bootstraps a random first user. When it
already has users, credentials must be supplied through
``JUNJO_STUDIO_E2E_EXISTING_EMAIL`` and
``JUNJO_STUDIO_E2E_EXISTING_PASSWORD``; those credentials are used only to
create the random test user. The random user and API key are deleted at the end
of the run. Credential values are never command-line arguments or output.

Run from the repository root with the Python SDK environment:

    uv run --project sdks/python python tooling/scripts/validate_agent_studio_e2e.py
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import http.cookiejar
import json
import os
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

SERVICE_NAMESPACE = "junjo.e2e"
SERVICE_VERSION = "horizon-1"
AGENT_KEY = "h1_studio_e2e_agent"
AGENT_NAME = "Horizon 1 Studio E2E Agent"
WORKFLOW_NAME = "Horizon 1 Normalization Workflow"
INPUT_VALUE = "Junjo horizon one e2e"
OUTPUT_VALUE = "JUNJO HORIZON ONE E2E"
FULL_POLICY = "junjo.full.v1"
EXISTING_EMAIL_ENV = "JUNJO_STUDIO_E2E_EXISTING_EMAIL"
EXISTING_PASSWORD_ENV = "JUNJO_STUDIO_E2E_EXISTING_PASSWORD"


class StudioE2EError(RuntimeError):
    """A safe, credential-free validation failure."""


class StudioHttpError(StudioE2EError):
    """One Studio HTTP response that did not satisfy the requested operation."""

    def __init__(self, *, method: str, path: str, status: int) -> None:
        super().__init__(f"Studio returned HTTP {status}: {method} {path}")
        self.status = status


def require(condition: bool, message: str) -> None:
    """Raise one explicit E2E failure when a contract is not satisfied."""

    if not condition:
        raise StudioE2EError(message)


class JsonClient:
    """Small JSON client with one isolated Studio session cookie jar."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        parsed = urllib.parse.urlparse(base_url)
        require(
            parsed.scheme in {"http", "https"} and bool(parsed.netloc),
            "--backend-url must be an absolute HTTP(S) URL",
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Mapping[str, object] | None = None,
    ) -> Any:
        """Issue one request without ever including request values in errors."""

        require(path.startswith("/"), "Studio API paths must begin with '/'")
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if encoded is not None else {}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=encoded,
            method=method,
            headers=headers,
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            error.read()
            raise StudioHttpError(
                method=method,
                path=path,
                status=error.code,
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise StudioE2EError(f"Studio API request failed: {method} {path}") from error
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise StudioE2EError(f"Studio returned invalid JSON: {method} {path}") from error


T = TypeVar("T")


def bounded_poll(
    operation: Callable[[], T],
    *,
    accept: Callable[[T], bool],
    timeout_seconds: float,
    interval_seconds: float,
    description: str,
    retry_statuses: frozenset[int] = frozenset({404, 409, 422, 503}),
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    """Poll one observable condition until accepted or the monotonic deadline."""

    require(timeout_seconds > 0, "poll timeout must be positive")
    require(interval_seconds > 0, "poll interval must be positive")
    deadline = clock() + timeout_seconds
    attempts = 0
    last_status: int | None = None
    while True:
        attempts += 1
        try:
            value = operation()
        except StudioHttpError as error:
            if error.status not in retry_statuses:
                raise
            last_status = error.status
        else:
            if accept(value):
                return value

        now = clock()
        if now >= deadline:
            suffix = f"; last HTTP status was {last_status}" if last_status else ""
            raise StudioE2EError(f"Timed out after {attempts} attempts waiting for {description}{suffix}")
        sleeper(min(interval_seconds, deadline - now))


@dataclass(frozen=True, slots=True)
class TestIdentity:
    """The random Studio user and API key owned by one validator run."""

    email: str
    password: str
    user_id: str
    api_key_id: str
    api_key: str


@dataclass(frozen=True, slots=True)
class ExecutionExpectations:
    """Detached facts returned by the real local Junjo execution."""

    service_name: str
    agent_runtime_id: str
    agent_definition_id: str
    agent_structural_id: str
    workflow_runtime_id: str
    workflow_definition_id: str
    workflow_start: dict[str, object]
    workflow_end: dict[str, object]


def _require_object(value: object, description: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{description} must be a JSON object")
    return value


def _require_list(value: object, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be a JSON array")
    return value


def wait_for_health(client: JsonClient, *, timeout_seconds: float, interval_seconds: float) -> None:
    """Wait only at the bounded Studio-health boundary."""

    health = bounded_poll(
        lambda: client.request("/health"),
        accept=lambda value: isinstance(value, dict) and value.get("status") == "ok",
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description="Studio backend health",
    )
    require(health["status"] == "ok", "Studio health response changed unexpectedly")


def provision_test_identity(client: JsonClient) -> TestIdentity:
    """Create and authenticate one random user, then create one random API key."""

    has_users_response = _require_object(
        client.request("/users/db-has-users"),
        "db-has-users response",
    )
    require(
        isinstance(has_users_response.get("users_exist"), bool),
        "db-has-users response must contain users_exist",
    )

    # Studio uses EmailStr with deliverability-aware validation, which correctly
    # rejects RFC-reserved domains such as ``example.invalid``.  ``example.com``
    # remains non-operational for this local identity while satisfying the same
    # public request contract exercised by real users.
    test_email = f"junjo-e2e-{secrets.token_hex(10)}@example.com"
    test_password = secrets.token_urlsafe(36)
    credentials = {"email": test_email, "password": test_password}
    test_user_created = False
    api_key_id: str | None = None
    try:
        if has_users_response["users_exist"]:
            existing_email = os.environ.get(EXISTING_EMAIL_ENV)
            existing_password = os.environ.get(EXISTING_PASSWORD_ENV)
            require(
                bool(existing_email and existing_password),
                "Studio already has users; provide existing local credentials through "
                f"{EXISTING_EMAIL_ENV} and {EXISTING_PASSWORD_ENV}",
            )
            client.request(
                "/sign-in",
                method="POST",
                body={"email": existing_email, "password": existing_password},
            )
            client.request("/users", method="POST", body=credentials)
            test_user_created = True
            client.request("/sign-out", method="POST")
            client.request("/sign-in", method="POST", body=credentials)
        else:
            client.request(
                "/users/create-first-user",
                method="POST",
                body=credentials,
            )
            test_user_created = True

        authenticated = _require_object(client.request("/auth-test"), "auth-test response")
        require(
            authenticated.get("user_email") == test_email,
            "Studio did not authenticate the fresh E2E user",
        )
        users = _require_list(client.request("/users"), "users response")
        matches = [user for user in users if isinstance(user, dict) and user.get("email") == test_email]
        require(len(matches) == 1, "Studio did not return exactly one fresh E2E user")
        user_id = matches[0].get("id")
        require(isinstance(user_id, str) and bool(user_id), "E2E user ID is missing")

        created_key = _require_object(
            client.request(
                "/api_keys",
                method="POST",
                body={"name": "Junjo Agent Horizon 1 E2E"},
            ),
            "API-key response",
        )
        raw_api_key_id = created_key.get("id")
        api_key = created_key.get("key")
        require(
            isinstance(raw_api_key_id, str) and bool(raw_api_key_id),
            "Studio did not return an API-key ID",
        )
        api_key_id = raw_api_key_id
        require(
            isinstance(api_key, str) and len(api_key) >= 32,
            "Studio did not return a valid API key",
        )
        return TestIdentity(
            email=test_email,
            password=test_password,
            user_id=user_id,
            api_key_id=api_key_id,
            api_key=api_key,
        )
    except BaseException as error:
        if test_user_created:
            cleanup_failures = _cleanup_partial_identity(
                client,
                email=test_email,
                password=test_password,
                api_key_id=api_key_id,
            )
            if cleanup_failures:
                error.add_note("Fresh E2E auth cleanup also failed at: " + ", ".join(cleanup_failures))
        raise


def _cleanup_partial_identity(
    client: JsonClient,
    *,
    email: str,
    password: str,
    api_key_id: str | None,
) -> list[str]:
    """Best-effort cleanup when auth provisioning fails before ownership returns."""

    failures: list[str] = []
    try:
        client.request(
            "/sign-in",
            method="POST",
            body={"email": email, "password": password},
        )
    except BaseException:
        return ["sign-in"]
    if api_key_id is not None:
        try:
            client.request(f"/api_keys/{api_key_id}", method="DELETE")
        except BaseException:
            failures.append("API-key deletion")
    try:
        users = _require_list(client.request("/users"), "users response")
        user_ids = [user.get("id") for user in users if isinstance(user, dict) and user.get("email") == email]
        if len(user_ids) != 1 or not isinstance(user_ids[0], str):
            failures.append("user lookup")
        else:
            client.request(f"/users/{user_ids[0]}", method="DELETE")
    except BaseException:
        failures.append("user deletion")
    try:
        client.request("/sign-out", method="POST")
    except BaseException:
        failures.append("sign-out")
    return failures


def cleanup_test_identity(client: JsonClient, identity: TestIdentity) -> None:
    """Delete only artifacts created by this validator run."""

    client.request(f"/api_keys/{identity.api_key_id}", method="DELETE")
    client.request(f"/users/{identity.user_id}", method="DELETE")
    client.request("/sign-out", method="POST")


async def _execute_public_composition() -> ExecutionExpectations:
    """Run one real public Agent -> Tool -> Workflow -> Nodes composition."""

    from junjo.agent import (
        FinalOutputResponse,
        ModelUsage,
        ToolCall,
        ToolCallsResponse,
    )
    from junjo.agent.testing import ScriptedModelDriver
    from pydantic import BaseModel, Field

    from junjo import (
        Agent,
        AgentLimits,
        BaseState,
        BaseStore,
        Edge,
        Graph,
        ModelDriverBinding,
        ModelDriverDescriptor,
        Node,
        Tool,
        Workflow,
    )

    class AgentInput(BaseModel):
        value: str

    class AgentOutput(BaseModel):
        value: str
        evidence: str

    class WorkflowToolInput(BaseModel):
        value: str

    class WorkflowToolOutput(BaseModel):
        value: str
        stages: list[str]

    class NormalizationState(BaseState):
        value: str
        stages: list[str] = Field(default_factory=list)

    class NormalizationStore(BaseStore[NormalizationState]):
        async def record_prepared(self) -> None:
            state = await self.get_state()
            await self.set_state({"stages": [*state.stages, "prepared"]})

        async def record_normalized(self) -> None:
            state = await self.get_state()
            await self.set_state(
                {
                    "value": state.value.upper(),
                    "stages": [*state.stages, "normalized"],
                }
            )

    class PrepareNormalizationNode(Node[NormalizationStore]):
        async def service(self, store: NormalizationStore) -> None:
            await store.record_prepared()

    class UppercaseNormalizationNode(Node[NormalizationStore]):
        async def service(self, store: NormalizationStore) -> None:
            await store.record_normalized()

    workflow_results: list[object] = []

    async def run_workflow(input: WorkflowToolInput, context: object) -> WorkflowToolOutput:
        del context

        def graph_factory() -> Graph:
            prepare = PrepareNormalizationNode()
            normalize = UppercaseNormalizationNode()
            return Graph(
                source=prepare,
                sinks=[normalize],
                edges=[Edge(tail=prepare, head=normalize)],
            )

        workflow = Workflow[
            NormalizationState,
            NormalizationStore,
        ](
            name=WORKFLOW_NAME,
            graph_factory=graph_factory,
            store_factory=lambda: NormalizationStore(NormalizationState(value=input.value)),
            max_iterations=1,
        )
        result = await workflow.execute()
        workflow_results.append(result)
        return WorkflowToolOutput(
            value=result.state.value,
            stages=result.state.stages,
        )

    workflow_tool = Tool[
        WorkflowToolInput,
        WorkflowToolOutput,
        None,
    ](
        name="run_normalization_workflow",
        description="Run the deterministic normalization Workflow.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=run_workflow,
    )
    usage_one = ModelUsage(input_tokens=7, output_tokens=2, total_tokens=9)
    usage_two = ModelUsage(input_tokens=11, output_tokens=3, total_tokens=14)
    driver = ScriptedModelDriver(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="h1-workflow-call",
                        name="run_normalization_workflow",
                        arguments={"value": INPUT_VALUE},
                    )
                ],
                assistant_text="Using the deterministic Workflow capability.",
                usage=usage_one,
            ),
            FinalOutputResponse(
                output={"value": OUTPUT_VALUE, "evidence": "nested_workflow"},
                usage=usage_two,
            ),
        ]
    )
    agent = Agent[AgentInput, AgentOutput, None](
        key=AGENT_KEY,
        name=AGENT_NAME,
        instructions="Use the declared Workflow Tool, then return its normalized value.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="h1-e2e-v1",
            ),
            driver=driver,
        ),
        tools=[workflow_tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )

    result = await agent.execute(AgentInput(value=INPUT_VALUE), dependencies=None)
    require(result.output.value == OUTPUT_VALUE, "local Agent output is incorrect")
    require(
        result.output.evidence == "nested_workflow",
        "local Agent output lost its evidence marker",
    )
    require(result.model_request_count == 2, "local Agent model count is incorrect")
    require(result.tool_call_requested_count == 1, "local requested Tool count is incorrect")
    require(result.tool_call_admitted_count == 1, "local admitted Tool count is incorrect")
    require(result.tool_call_started_count == 1, "local started Tool count is incorrect")
    require(result.tool_call_completed_count == 1, "local completed Tool count is incorrect")
    require(len(workflow_results) == 1, "Workflow Tool did not execute exactly once")

    workflow_result = workflow_results[0]
    workflow_state = workflow_result.state
    require(workflow_state.value == OUTPUT_VALUE, "local Workflow output is incorrect")
    require(
        workflow_state.stages == ["prepared", "normalized"],
        "local Workflow stages are incorrect",
    )
    return ExecutionExpectations(
        service_name="",  # Assigned by the caller's unique OTel resource.
        agent_runtime_id=result.run_id,
        agent_definition_id=result.definition_id,
        agent_structural_id=result.structural_id,
        workflow_runtime_id=workflow_result.run_id,
        workflow_definition_id=workflow_result.definition_id,
        workflow_start={"value": INPUT_VALUE, "stages": []},
        workflow_end={
            "value": OUTPUT_VALUE,
            "stages": ["prepared", "normalized"],
        },
    )


def execute_and_export(
    *,
    api_key: str,
    ingestion_host: str,
    ingestion_port: int,
    service_name: str,
    timeout_seconds: float,
) -> ExecutionExpectations:
    """Own one OpenTelemetry provider, execute, flush, and shut it down."""

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.namespace": SERVICE_NAMESPACE,
            "service.name": service_name,
            "service.version": SERVICE_VERSION,
        }
    )
    exporter = OTLPSpanExporter(
        endpoint=f"{ingestion_host}:{ingestion_port}",
        insecure=True,
        headers=(("x-junjo-api-key", api_key),),
        timeout=min(timeout_seconds, 120),
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    try:
        expectations = asyncio.run(_execute_public_composition())
        flushed = provider.force_flush(timeout_millis=int(timeout_seconds * 1000))
        require(flushed, "OpenTelemetry provider did not flush Agent evidence")
    finally:
        provider.shutdown()
    return ExecutionExpectations(
        service_name=service_name,
        agent_runtime_id=expectations.agent_runtime_id,
        agent_definition_id=expectations.agent_definition_id,
        agent_structural_id=expectations.agent_structural_id,
        workflow_runtime_id=expectations.workflow_runtime_id,
        workflow_definition_id=expectations.workflow_definition_id,
        workflow_start=expectations.workflow_start,
        workflow_end=expectations.workflow_end,
    )


def assert_full_payload(payload: object, description: str) -> Any:
    """Require one inspectable full-policy payload slot and return its value."""

    slot = _require_object(payload, description)
    require(slot.get("mode") == "full", f"{description} must use full mode")
    require(slot.get("policy") == FULL_POLICY, f"{description} policy is incorrect")
    require("value" in slot, f"{description} must contain a value")
    require(slot.get("reference") is None, f"{description} cannot contain a reference")
    require(slot.get("reason") is None, f"{description} cannot contain an absence reason")
    return slot["value"]


def assert_verified_store(
    store: object,
    *,
    expected_start: object,
    expected_end: object,
    expected_actions: Sequence[str] | None,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> None:
    """Independently replay one backend-verified full-evidence Store timeline."""

    detail = _require_object(store, "Store detail")
    require(detail.get("available") is True, "Store must be available")
    require(detail.get("reconstructable_claimed") is True, "producer Store claim must be true")
    require(detail.get("reconstructable") is True, "backend Store replay must be verified")
    require(
        detail.get("reconstruction_status") == "verified",
        "Store reconstruction status must be verified",
    )
    require(detail.get("reconstruction_reason") is None, "verified Store cannot have a reason")
    require(isinstance(detail.get("store_id"), str), "Store ID is missing")
    start = assert_full_payload(detail.get("start"), "Store start")
    end = assert_full_payload(detail.get("end"), "Store end")
    require(start == expected_start, "Store start state is incorrect")
    require(end == expected_end, "Store end state is incorrect")

    transitions = _require_list(detail.get("transitions"), "Store transitions")
    transition_count = detail.get("transition_count")
    require(transition_count == len(transitions), "Store transition count is inconsistent")
    revision_start = detail.get("revision_start")
    revision_end = detail.get("revision_end")
    require(isinstance(revision_start, int), "Store start revision is missing")
    require(isinstance(revision_end, int), "Store end revision is missing")

    current = copy.deepcopy(start)
    previous_revision = revision_start
    observed_actions: list[str] = []
    for sequence, raw_transition in enumerate(transitions, start=1):
        transition = _require_object(raw_transition, f"Store transition {sequence}")
        require(transition.get("sequence") == sequence, "Store transition sequence is not contiguous")
        require(
            transition.get("revision_before") == previous_revision,
            "Store revision chain is discontinuous",
        )
        revision_after = transition.get("revision_after")
        require(
            isinstance(revision_after, int) and revision_after in {previous_revision, previous_revision + 1},
            "Store revision step is invalid",
        )
        require(transition.get("before") == current, "backend Store before projection is incorrect")
        patch_value = assert_full_payload(
            transition.get("patch"),
            f"Store transition {sequence} patch",
        )
        patch = _require_list(patch_value, f"Store transition {sequence} patch value")
        replayed = apply_patch(copy.deepcopy(current), patch)
        require(transition.get("after") == replayed, "backend Store after projection is incorrect")
        current = replayed
        previous_revision = revision_after
        action = transition.get("action")
        require(isinstance(action, str) and bool(action), "Store transition action is missing")
        observed_actions.append(action)

    require(previous_revision == revision_end, "Store terminal revision is incorrect")
    require(current == end, "independent Store replay did not produce the emitted end state")
    if expected_actions is not None:
        require(observed_actions == list(expected_actions), "Store action sequence is incorrect")


def assert_agent_semantics(
    *,
    summary: object,
    detail: object,
    expectations: ExecutionExpectations,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> tuple[str, str, str]:
    """Validate the exact semantic Agent result and return nested Workflow IDs."""

    listed = _require_object(summary, "Agent summary")
    projection = _require_object(detail, "Agent detail")
    require(projection.get("summary") == listed, "Agent list/detail summaries diverged")
    service = _require_object(listed.get("service"), "Agent service identity")
    require(
        service
        == {
            "namespace": SERVICE_NAMESPACE,
            "name": expectations.service_name,
            "version": SERVICE_VERSION,
        },
        "Agent service scope is incorrect",
    )
    require(listed.get("agent_key") == AGENT_KEY, "Agent key is incorrect")
    require(listed.get("agent_name") == AGENT_NAME, "Agent name is incorrect")
    require(listed.get("runtime_id") == expectations.agent_runtime_id, "Agent runtime ID is incorrect")
    require(
        listed.get("definition_id") == expectations.agent_definition_id,
        "Agent definition ID is incorrect",
    )
    require(
        listed.get("structural_id") == expectations.agent_structural_id,
        "Agent structural ID is incorrect",
    )
    require(listed.get("outcome") == "completed", "Agent did not complete")
    require(listed.get("termination_reason") == "final_output", "Agent termination reason is incorrect")
    require(listed.get("limits") == {"model_requests": 2, "tool_calls": 1}, "Agent limits are incorrect")
    require(
        listed.get("counts")
        == {
            "operations": 3,
            "model_requests": 2,
            "tool_calls": {
                "requested": 1,
                "admitted": 1,
                "started": 1,
                "completed": 1,
            },
        },
        "Agent operation counts are incorrect",
    )
    require(
        listed.get("usage")
        == {
            "model_responses": 2,
            "fields": {
                "inputTokens": {"sum": 18, "observations": 2},
                "outputTokens": {"sum": 5, "observations": 2},
                "totalTokens": {"sum": 23, "observations": 2},
            },
        },
        "Agent usage aggregate is incorrect",
    )
    integrity = _require_object(projection.get("integrity"), "Agent integrity")
    require(integrity.get("status") == "complete", "Agent evidence is not complete")
    require(integrity.get("diagnostics") == [], "Agent evidence has diagnostics")
    require(
        all(value == 0 for value in _require_object(integrity.get("loss_counts"), "Agent loss counts").values()),
        "Agent evidence has OTLP loss",
    )
    require(projection.get("parent_executable") is None, "standalone Agent fabricated a semantic parent")
    require(projection.get("error") is None, "completed Agent contains an error")
    require(projection.get("cancellation") is None, "completed Agent contains cancellation")
    assert_full_payload(projection.get("definition"), "Agent definition")
    require(
        assert_full_payload(projection.get("input"), "Agent input") == {"value": INPUT_VALUE},
        "Agent input payload is incorrect",
    )
    require(
        assert_full_payload(projection.get("output"), "Agent output")
        == {"value": OUTPUT_VALUE, "evidence": "nested_workflow"},
        "Agent output payload is incorrect",
    )

    operations = _require_list(projection.get("operations"), "Agent operations")
    require(
        [operation.get("operation_type") for operation in operations] == ["model_request", "tool", "model_request"],
        "Agent operation types are not in realized order",
    )
    require(
        [operation.get("sequence") for operation in operations] == [1, 2, 3],
        "Agent operation sequence is not contiguous",
    )
    first_model, tool_operation, second_model = operations
    for ordinal, model_operation in enumerate((first_model, second_model), start=1):
        require(model_operation.get("ordinal") == ordinal, "model ordinal is incorrect")
        require(model_operation.get("outcome") == "completed", "model operation did not complete")
        assert_full_payload(model_operation.get("request"), f"model request {ordinal}")
        candidate = _require_object(
            model_operation.get("response_candidate"),
            f"model response candidate {ordinal}",
        )
        require(candidate.get("available") is True, "model response candidate is unavailable")
        assert_full_payload(candidate.get("payload"), f"model response candidate {ordinal} payload")
        assert_full_payload(model_operation.get("response"), f"model response {ordinal}")
    require(first_model.get("response_type") == "tool_calls", "first model response type is incorrect")
    require(second_model.get("response_type") == "final_output", "second model response type is incorrect")
    requested_calls = _require_list(first_model.get("requested_tool_calls"), "requested Tool calls")
    require(
        requested_calls
        == [
            {
                "call_id": "h1-workflow-call",
                "ordinal": 1,
                "tool_name": "run_normalization_workflow",
                "observed_tool_operation": True,
                "admission": "admitted",
                "reason": None,
            }
        ],
        "requested Tool-call projection is incorrect",
    )
    require(tool_operation.get("call_id") == "h1-workflow-call", "Tool call ID is incorrect")
    require(tool_operation.get("ordinal") == 1, "Tool call ordinal is incorrect")
    require(tool_operation.get("outcome") == "completed", "Tool operation did not complete")
    require(
        assert_full_payload(tool_operation.get("requested_arguments"), "Tool requested arguments")
        == {"value": INPUT_VALUE},
        "Tool requested arguments are incorrect",
    )
    require(
        assert_full_payload(tool_operation.get("arguments"), "Tool validated arguments") == {"value": INPUT_VALUE},
        "Tool validated arguments are incorrect",
    )
    result_candidate = _require_object(tool_operation.get("result_candidate"), "Tool result candidate")
    require(result_candidate.get("available") is True, "Tool result candidate is unavailable")
    expected_tool_result = {"value": OUTPUT_VALUE, "stages": ["prepared", "normalized"]}
    require(
        assert_full_payload(result_candidate.get("payload"), "Tool result candidate payload") == expected_tool_result,
        "Tool result candidate is incorrect",
    )
    require(
        assert_full_payload(tool_operation.get("result"), "Tool result") == expected_tool_result,
        "Tool result is incorrect",
    )

    assert_verified_store(
        projection.get("state"),
        expected_start=_agent_state_boundary(final=False),
        expected_end=_agent_state_boundary(final=True),
        expected_actions=None,
        apply_patch=apply_patch,
    )
    agent_state = _require_object(projection.get("state"), "Agent Store")
    require(
        agent_state.get("transition_count") == agent_state.get("revision_end"),
        "this Agent proof expects every transition to change state",
    )

    nested = _require_list(projection.get("nested_executables"), "nested executables")
    require(len(nested) == 1, "Agent must expose exactly one nested Workflow")
    workflow = _require_object(nested[0], "nested Workflow reference")
    require(workflow.get("executable_type") == "workflow", "nested executable is not a Workflow")
    require(workflow.get("name") == WORKFLOW_NAME, "nested Workflow name is incorrect")
    require(
        workflow.get("runtime_id") == expectations.workflow_runtime_id,
        "nested Workflow runtime ID is incorrect",
    )
    require(
        workflow.get("definition_id") == expectations.workflow_definition_id,
        "nested Workflow definition ID is incorrect",
    )
    require(workflow.get("parent_operation_sequence") == 2, "nested Workflow operation link is incorrect")
    require(
        workflow.get("parent_operation_span_id") == tool_operation.get("span_id"),
        "nested Workflow does not link to its physical Tool parent",
    )
    require(workflow.get("trace_id") == listed.get("trace_id"), "nested Workflow left the Agent trace")
    trace_id = workflow.get("trace_id")
    workflow_span_id = workflow.get("span_id")
    tool_span_id = tool_operation.get("span_id")
    require(
        all(isinstance(value, str) for value in (trace_id, workflow_span_id, tool_span_id)),
        "semantic execution IDs are missing",
    )
    return trace_id, workflow_span_id, tool_span_id


def _agent_state_boundary(*, final: bool) -> dict[str, object]:
    """Return the exact normalized start or end Agent state for this proof."""

    transcript: list[dict[str, object]] = [
        {"type": "agent_input", "input": {"value": INPUT_VALUE}},
    ]
    if final:
        transcript.extend(
            [
                {
                    "type": "assistant_tool_calls",
                    "calls": [
                        {
                            "id": "h1-workflow-call",
                            "name": "run_normalization_workflow",
                            "arguments": {"value": INPUT_VALUE},
                        }
                    ],
                    "assistantText": "Using the deterministic Workflow capability.",
                },
                {
                    "type": "tool_result",
                    "callId": "h1-workflow-call",
                    "toolName": "run_normalization_workflow",
                    "result": {
                        "value": OUTPUT_VALUE,
                        "stages": ["prepared", "normalized"],
                    },
                },
                {
                    "type": "assistant_output",
                    "output": {"value": OUTPUT_VALUE, "evidence": "nested_workflow"},
                },
            ]
        )
    return {
        "input": {"value": INPUT_VALUE},
        "history": [],
        "transcript": transcript,
        "model_iteration": 2 if final else 0,
        "model_request_count": 2 if final else 0,
        "tool_call_requested_count": 1 if final else 0,
        "tool_call_admitted_count": 1 if final else 0,
        "tool_call_started_count": 1 if final else 0,
        "tool_call_completed_count": 1 if final else 0,
        "admitted_tool_call_ids": ["h1-workflow-call"] if final else [],
        "pending_tool_call_ids": [],
        "completed_tool_call_ids": ["h1-workflow-call"] if final else [],
        "usage": {
            "v": 1,
            "modelResponses": 2 if final else 0,
            "fields": (
                {
                    "inputTokens": {"sum": 18, "observations": 2},
                    "outputTokens": {"sum": 5, "observations": 2},
                    "totalTokens": {"sum": 23, "observations": 2},
                }
                if final
                else {}
            ),
        },
        "final_output_available": final,
        "final_output": ({"value": OUTPUT_VALUE, "evidence": "nested_workflow"} if final else None),
        "terminal_reason": "final_output" if final else None,
    }


def assert_workflow_semantics(
    projection: object,
    *,
    trace_id: str,
    workflow_span_id: str,
    expectations: ExecutionExpectations,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> None:
    """Validate the nested Workflow's backend-authoritative Store projection."""

    workflow = _require_object(projection, "Workflow Store diagnostic")
    require(workflow.get("trace_id") == trace_id, "Workflow diagnostic trace ID is incorrect")
    require(
        workflow.get("workflow_span_id") == workflow_span_id,
        "Workflow diagnostic span ID is incorrect",
    )
    require(workflow.get("executable_type") == "workflow", "Workflow diagnostic type is incorrect")
    require(workflow.get("name") == WORKFLOW_NAME, "Workflow diagnostic name is incorrect")
    integrity = _require_object(workflow.get("integrity"), "Workflow integrity")
    require(integrity.get("status") == "complete", "Workflow evidence is not complete")
    require(integrity.get("diagnostics") == [], "Workflow evidence has diagnostics")
    require(
        all(value == 0 for value in _require_object(integrity.get("loss_counts"), "Workflow loss counts").values()),
        "Workflow evidence has OTLP loss",
    )
    assert_verified_store(
        workflow.get("state"),
        expected_start=expectations.workflow_start,
        expected_end=expectations.workflow_end,
        expected_actions=["record_prepared", "record_normalized"],
        apply_patch=apply_patch,
    )
    state = _require_object(workflow.get("state"), "Workflow Store")
    require(state.get("revision_start") == 0, "Workflow Store must start at revision zero")
    require(state.get("revision_end") == 2, "Workflow Store must end at revision two")
    require(state.get("transition_count") == 2, "Workflow Store must expose two transitions")


def assert_raw_hierarchy(
    raw_spans: object,
    *,
    detail: object,
    trace_id: str,
    workflow_span_id: str,
    tool_span_id: str,
    expectations: ExecutionExpectations,
) -> None:
    """Validate exact physical OTLP parentage independently from semantic links."""

    spans = _require_list(raw_spans, "raw trace spans")
    require(len(spans) == 7, "provider-free proof must emit exactly seven Junjo spans")
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw_span in enumerate(spans):
        span = _require_object(raw_span, f"raw span {index}")
        span_id = span.get("span_id")
        require(isinstance(span_id, str) and span_id not in by_id, "raw span IDs must be unique")
        by_id[span_id] = span
        require(span.get("trace_id") == trace_id, "raw span left the expected trace")
        require(span.get("service_name") == expectations.service_name, "raw span service name is incorrect")
        resource = _require_object(span.get("resource_attributes_json"), "raw span resource")
        require(resource.get("service.namespace") == SERVICE_NAMESPACE, "raw service namespace is incorrect")
        require(resource.get("service.name") == expectations.service_name, "raw resource service name is incorrect")
        require(resource.get("service.version") == SERVICE_VERSION, "raw service version is incorrect")
        require(span.get("dropped_attributes_count") == 0, "raw span dropped attributes")
        require(span.get("dropped_events_count") == 0, "raw span dropped events")
        require(span.get("dropped_links_count") == 0, "raw span dropped links")
        require(span.get("resource_dropped_attributes_count") == 0, "raw resource dropped attributes")

    projection = _require_object(detail, "Agent detail")
    summary = _require_object(projection.get("summary"), "Agent summary")
    agent_span_id = summary.get("agent_span_id")
    require(isinstance(agent_span_id, str) and agent_span_id in by_id, "raw Agent span is missing")
    agent_span = by_id[agent_span_id]
    require(agent_span.get("parent_span_id") in {None, ""}, "standalone Agent is not a physical root")
    agent_attributes = _require_object(agent_span.get("attributes_json"), "raw Agent attributes")
    require(agent_attributes.get("junjo.span_type") == "agent", "raw Agent type is incorrect")

    operations = _require_list(projection.get("operations"), "Agent operations")
    operation_ids = [operation.get("span_id") for operation in operations]
    require(
        all(isinstance(span_id, str) and span_id in by_id for span_id in operation_ids),
        "raw operations are missing",
    )
    for operation, operation_id in zip(operations, operation_ids, strict=True):
        operation_span = by_id[operation_id]
        require(operation_span.get("parent_span_id") == agent_span_id, "operation is not a direct Agent child")
        attributes = _require_object(operation_span.get("attributes_json"), "raw operation attributes")
        require(
            attributes.get("junjo.agent.operation_type") == operation.get("operation_type"),
            "raw operation type disagrees with semantic projection",
        )
        require(
            attributes.get("junjo.agent.runtime_id") == expectations.agent_runtime_id,
            "raw operation owner is incorrect",
        )

    require(tool_span_id in by_id, "raw Tool span is missing")
    require(workflow_span_id in by_id, "raw nested Workflow span is missing")
    workflow_span = by_id[workflow_span_id]
    require(workflow_span.get("parent_span_id") == tool_span_id, "nested Workflow is not a physical Tool child")
    workflow_attributes = _require_object(workflow_span.get("attributes_json"), "raw Workflow attributes")
    require(workflow_attributes.get("junjo.span_type") == "workflow", "raw Workflow type is incorrect")
    require(
        workflow_attributes.get("junjo.parent_executable_definition_id") == expectations.agent_definition_id,
        "nested Workflow semantic parent definition is incorrect",
    )
    require(
        workflow_attributes.get("junjo.parent_executable_runtime_id") == expectations.agent_runtime_id,
        "nested Workflow semantic parent runtime is incorrect",
    )
    require(
        workflow_attributes.get("junjo.parent_executable_structural_id") == expectations.agent_structural_id,
        "nested Workflow semantic parent structural ID is incorrect",
    )
    require(
        workflow_attributes.get("junjo.parent_executable_type") == "agent",
        "nested Workflow semantic parent type is incorrect",
    )
    nodes = [
        span
        for span in spans
        if isinstance(span.get("attributes_json"), dict) and span["attributes_json"].get("junjo.span_type") == "node"
    ]
    require(len(nodes) == 2, "nested Workflow must emit exactly two Node spans")
    require(
        {node.get("name") for node in nodes} == {"PrepareNormalizationNode", "UppercaseNormalizationNode"},
        "nested Workflow Node names are incorrect",
    )
    require(
        all(node.get("parent_span_id") == workflow_span_id for node in nodes),
        "nested Workflow Nodes are not physical Workflow children",
    )


def build_browser_evidence(
    *,
    summary: Mapping[str, object],
    expectations: ExecutionExpectations,
    trace_id: str,
    workflow_span_id: str,
    tool_span_id: str,
) -> dict[str, object]:
    """Build the credential-free identity handoff for the Studio browser proof."""

    agent_span_id = summary.get("span_id")
    require(isinstance(agent_span_id, str), "Agent summary span ID is missing")
    return {
        "schema_version": 1,
        "service_namespace": SERVICE_NAMESPACE,
        "service_name": expectations.service_name,
        "service_version": SERVICE_VERSION,
        "trace_id": trace_id,
        "agent_name": AGENT_NAME,
        "agent_run_id": expectations.agent_runtime_id,
        "agent_span_id": agent_span_id,
        "tool_name": "run_normalization_workflow",
        "tool_operation_sequence": 2,
        "tool_span_id": tool_span_id,
        "nested_workflow_name": WORKFLOW_NAME,
        "nested_workflow_span_id": workflow_span_id,
    }


def write_browser_evidence(path: Path, evidence: Mapping[str, object]) -> None:
    """Atomically publish evidence only after the cross-layer proof succeeds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(evidence, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def fetch_agent_projection(
    client: JsonClient,
    *,
    expectations: ExecutionExpectations,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bounded-poll list and detail until the exact emitted run is queryable."""

    query = urllib.parse.urlencode(
        {
            "service_namespace": SERVICE_NAMESPACE,
            "service_name": expectations.service_name,
            "agent_key": AGENT_KEY,
            "limit": 10,
        }
    )

    def query_projection() -> tuple[dict[str, Any], dict[str, Any]] | None:
        summaries = _require_list(
            client.request(f"/api/v1/agent-executions?{query}"),
            "Agent execution list",
        )
        matches = [
            summary
            for summary in summaries
            if isinstance(summary, dict) and summary.get("runtime_id") == expectations.agent_runtime_id
        ]
        if not matches:
            return None
        require(len(matches) == 1, "Studio returned duplicate Agent runtime identities")
        summary = matches[0]
        trace_id = summary.get("trace_id")
        span_id = summary.get("agent_span_id")
        require(isinstance(trace_id, str) and isinstance(span_id, str), "Agent identity is incomplete")
        detail = _require_object(
            client.request(f"/api/v1/agent-executions/{trace_id}/{span_id}"),
            "Agent execution detail",
        )
        return summary, detail

    result = bounded_poll(
        query_projection,
        accept=lambda value: value is not None,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description="the emitted Agent semantic projection",
    )
    require(result is not None, "Agent semantic projection is absent")
    return result


def run(args: argparse.Namespace) -> None:
    """Execute one complete authenticated live cross-layer proof."""

    import jsonpatch

    backend = JsonClient(args.backend_url)
    wait_for_health(
        backend,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.poll_interval_seconds,
    )
    identity: TestIdentity | None = None
    browser_evidence: dict[str, object] | None = None
    primary_error: BaseException | None = None
    try:
        identity = provision_test_identity(backend)
        service_name = f"junjo-agent-h1-e2e-{secrets.token_hex(8)}"
        expectations = execute_and_export(
            api_key=identity.api_key,
            ingestion_host=args.ingestion_host,
            ingestion_port=args.ingestion_port,
            service_name=service_name,
            timeout_seconds=args.timeout_seconds,
        )
        summary, detail = fetch_agent_projection(
            backend,
            expectations=expectations,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )

        def apply_patch(document: object, patch: list[dict[str, object]]) -> object:
            return jsonpatch.JsonPatch(patch).apply(document, in_place=False)

        trace_id, workflow_span_id, tool_span_id = assert_agent_semantics(
            summary=summary,
            detail=detail,
            expectations=expectations,
            apply_patch=apply_patch,
        )
        workflow_projection = bounded_poll(
            lambda: backend.request(f"/api/v1/workflow-executions/{trace_id}/{workflow_span_id}/store"),
            accept=lambda value: isinstance(value, dict),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
            description="the nested Workflow Store projection",
        )
        assert_workflow_semantics(
            workflow_projection,
            trace_id=trace_id,
            workflow_span_id=workflow_span_id,
            expectations=expectations,
            apply_patch=apply_patch,
        )
        raw_spans = bounded_poll(
            lambda: backend.request(f"/api/v1/observability/traces/{trace_id}/spans"),
            accept=lambda value: isinstance(value, list) and len(value) == 7,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
            description="all seven raw OTLP spans",
        )
        assert_raw_hierarchy(
            raw_spans,
            detail=detail,
            trace_id=trace_id,
            workflow_span_id=workflow_span_id,
            tool_span_id=tool_span_id,
            expectations=expectations,
        )
        browser_evidence = build_browser_evidence(
            summary=summary,
            expectations=expectations,
            trace_id=trace_id,
            workflow_span_id=workflow_span_id,
            tool_span_id=tool_span_id,
        )
    except BaseException as error:
        primary_error = error
    cleanup_error: BaseException | None = None
    if identity is not None:
        try:
            cleanup_test_identity(backend, identity)
        except BaseException as error:
            cleanup_error = error
    if primary_error is not None:
        if cleanup_error is not None:
            print(
                f"warning: E2E auth cleanup also failed: {cleanup_error}",
                file=sys.stderr,
            )
        raise primary_error
    if cleanup_error is not None:
        raise cleanup_error
    if args.evidence_output is not None:
        require(browser_evidence is not None, "browser evidence was not produced")
        write_browser_evidence(args.evidence_output, browser_evidence)
    print(
        "Agent Studio E2E passed: real public SDK composition reached OTLP, raw "
        "Studio storage, Agent semantics, and verified Agent/Workflow Store replay.",
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit local Studio validation interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-url",
        default="http://127.0.0.1:26154",
        help="Local Studio backend base URL.",
    )
    parser.add_argument(
        "--ingestion-host",
        default="127.0.0.1",
        help="Local Studio OTLP gRPC host.",
    )
    parser.add_argument(
        "--ingestion-port",
        type=int,
        default=26155,
        help="Local Studio OTLP gRPC port.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--evidence-output",
        type=Path,
        help="Optional credential-free JSON identity handoff for a browser proof.",
    )
    return parser


def main() -> int:
    """Validate arguments and run the live proof."""

    args = build_parser().parse_args()
    require(0 < args.ingestion_port <= 65535, "--ingestion-port is invalid")
    require(bool(args.ingestion_host.strip()), "--ingestion-host cannot be empty")
    require(args.timeout_seconds > 0, "--timeout-seconds must be positive")
    require(
        args.poll_interval_seconds > 0,
        "--poll-interval-seconds must be positive",
    )
    run(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StudioE2EError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
