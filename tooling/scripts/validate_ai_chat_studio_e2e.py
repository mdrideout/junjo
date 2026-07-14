#!/usr/bin/env python3
"""Prove the Horizon 2 AI Chat -> Junjo -> OTLP -> Studio path live.

The proof starts at the real FastAPI boundary.  It posts one image turn through
the deterministic demo driver, verifies the synchronous response, persisted
messages, and generated SVG, then lets the application lifespan flush its
Junjo telemetry.  It subsequently queries an authenticated local Studio and
proves the exact eleven-span physical tree, Agent operation order, semantic
parentage, and independently replayable outer-Workflow, Agent, and nested-
Workflow Stores.

The target Studio must be a disposable local development instance.  Identity
provisioning and cleanup use the safe shared support in
``validate_agent_studio_e2e.py``; credentials are never command-line values or
output.

Run from the repository root after syncing the AI Chat workspace package:

    uv run --project sdks/python --package junjo-ai-chat-example \
        python tooling/scripts/validate_ai_chat_studio_e2e.py \
        --evidence-output /tmp/junjo-ai-chat-evidence.json
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import validate_agent_studio_e2e as studio_support

SERVICE_NAMESPACE = "junjo.examples"
SERVICE_NAME = "ai-chat"
AGENT_KEY = "ai_chat"
AGENT_NAME = "AI Chat Agent"
OUTER_WORKFLOW_NAME = "Chat Turn Workflow"
IMAGE_WORKFLOW_NAME = "Create Chat Image Workflow"
CONVERSATION_ID = "demo"
INPUT_TEXT = "Draw an image of a telemetry lighthouse"
ASSISTANT_TEXT = "I created the requested deterministic illustration."
IMAGE_ALT = f"Deterministic illustration: {INPUT_TEXT}"
EXPECTED_SPAN_COUNT = 11
FULL_POLICY = studio_support.FULL_POLICY


@dataclass(frozen=True, slots=True)
class TurnExpectations:
    """Detached HTTP facts needed to identify and validate one live trace."""

    service_version: str
    workflow_run_id: str
    agent_run_id: str
    turn_id: str
    user_message: dict[str, object]
    assistant_message: dict[str, object]
    image_id: str

    @property
    def image_url(self) -> str:
        return f"/api/images/{self.image_id}.svg"

    @property
    def artifact(self) -> dict[str, object]:
        return {
            "id": self.image_id,
            "url": self.image_url,
            "alt_text": IMAGE_ALT,
        }

    @property
    def agent_input(self) -> dict[str, object]:
        return {
            "conversation_id": CONVERSATION_ID,
            "turn_id": self.turn_id,
            "message": INPUT_TEXT,
        }

    @property
    def agent_output(self) -> dict[str, object]:
        return {"message": ASSISTANT_TEXT, "image": self.artifact}


@dataclass(frozen=True, slots=True)
class SemanticIdentities:
    """Span identities resolved from Studio's semantic Agent projection."""

    trace_id: str
    agent_span_id: str
    tool_span_id: str
    nested_workflow_span_id: str
    execute_agent_span_id: str


def build_live_evidence(
    *,
    expectations: TurnExpectations,
    identities: SemanticIdentities,
    outer_span_id: str,
) -> dict[str, object]:
    """Build the strict, credential-free handoff to Studio's browser proof."""

    return {
        "schema_version": 1,
        "service_namespace": SERVICE_NAMESPACE,
        "service_name": SERVICE_NAME,
        "service_version": expectations.service_version,
        "trace_id": identities.trace_id,
        "outer_workflow_name": OUTER_WORKFLOW_NAME,
        "outer_workflow_run_id": expectations.workflow_run_id,
        "outer_workflow_span_id": outer_span_id,
        "agent_name": AGENT_NAME,
        "agent_run_id": expectations.agent_run_id,
        "agent_span_id": identities.agent_span_id,
        "tool_name": "create_image",
        "tool_operation_sequence": 2,
        "tool_span_id": identities.tool_span_id,
        "nested_workflow_name": IMAGE_WORKFLOW_NAME,
        "nested_workflow_span_id": identities.nested_workflow_span_id,
    }


def write_live_evidence(path: Path, evidence: Mapping[str, object]) -> None:
    """Atomically publish evidence only after the entire live proof succeeds."""

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


def _object(value: object, description: str) -> dict[str, Any]:
    studio_support.require(
        isinstance(value, dict), f"{description} must be a JSON object"
    )
    return value


def _list(value: object, description: str) -> list[Any]:
    studio_support.require(
        isinstance(value, list), f"{description} must be a JSON array"
    )
    return value


def _nonempty_text(value: object, description: str) -> str:
    studio_support.require(
        isinstance(value, str) and bool(value), f"{description} is missing"
    )
    return value


def _exact_keys(
    value: Mapping[str, object], expected: set[str], description: str
) -> None:
    studio_support.require(
        set(value) == expected, f"{description} fields are incorrect"
    )


def _assert_utc_timestamp(value: object, description: str) -> None:
    text = _nonempty_text(value, description)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise studio_support.StudioE2EError(f"{description} is not ISO 8601") from error
    studio_support.require(
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.utcoffset().total_seconds() == 0,
        f"{description} must identify UTC",
    )


def assert_http_turn(
    *,
    turn_payload: object,
    persistence_payload: object,
    svg_status: int,
    svg_content_type: str,
    svg_text: str,
    service_version: str,
) -> TurnExpectations:
    """Validate the exact synchronous API and persistence projection."""

    turn = _object(turn_payload, "turn response")
    _exact_keys(
        turn,
        {
            "conversation_id",
            "workflow_run_id",
            "agent_run_id",
            "user_message",
            "assistant_message",
        },
        "turn response",
    )
    studio_support.require(
        turn.get("conversation_id") == CONVERSATION_ID, "turn conversation is incorrect"
    )
    workflow_run_id = _nonempty_text(turn.get("workflow_run_id"), "Workflow run ID")
    agent_run_id = _nonempty_text(turn.get("agent_run_id"), "Agent run ID")
    studio_support.require(
        workflow_run_id != agent_run_id,
        "Workflow and Agent run IDs must be independent",
    )

    user = _object(turn.get("user_message"), "user message")
    assistant = _object(turn.get("assistant_message"), "assistant message")
    message_keys = {
        "id",
        "turn_id",
        "role",
        "content",
        "image_url",
        "image_alt",
        "created_at",
    }
    _exact_keys(user, message_keys, "user message")
    _exact_keys(assistant, message_keys, "assistant message")
    turn_id = _nonempty_text(user.get("turn_id"), "turn ID")
    studio_support.require(
        assistant.get("turn_id") == turn_id, "response messages must share one turn ID"
    )
    studio_support.require(user.get("role") == "user", "user message role is incorrect")
    studio_support.require(
        user.get("content") == INPUT_TEXT, "user message content is incorrect"
    )
    studio_support.require(
        user.get("image_url") is None, "user message cannot contain an image URL"
    )
    studio_support.require(
        user.get("image_alt") is None, "user message cannot contain image alt text"
    )
    studio_support.require(
        assistant.get("role") == "assistant", "assistant message role is incorrect"
    )
    studio_support.require(
        assistant.get("content") == ASSISTANT_TEXT, "assistant content is incorrect"
    )
    studio_support.require(
        assistant.get("image_alt") == IMAGE_ALT, "assistant image alt text is incorrect"
    )
    _nonempty_text(user.get("id"), "user message ID")
    _nonempty_text(assistant.get("id"), "assistant message ID")
    studio_support.require(
        user.get("id") != assistant.get("id"), "message IDs must be independent"
    )
    _assert_utc_timestamp(user.get("created_at"), "user message timestamp")
    _assert_utc_timestamp(assistant.get("created_at"), "assistant message timestamp")

    image_url = _nonempty_text(assistant.get("image_url"), "assistant image URL")
    image_match = re.fullmatch(r"/api/images/([0-9a-f]{32})\.svg", image_url)
    studio_support.require(
        image_match is not None,
        "assistant image URL is not an owned deterministic artifact",
    )
    assert image_match is not None
    image_id = image_match.group(1)

    persisted = _object(persistence_payload, "message-list response")
    _exact_keys(persisted, {"conversation_id", "messages"}, "message-list response")
    studio_support.require(
        persisted.get("conversation_id") == CONVERSATION_ID,
        "persisted conversation identity is incorrect",
    )
    studio_support.require(
        persisted.get("messages") == [user, assistant],
        "persisted messages do not exactly match the synchronous response",
    )

    studio_support.require(
        svg_status == 200, "generated image endpoint did not return HTTP 200"
    )
    studio_support.require(
        svg_content_type.split(";", 1)[0].strip() == "image/svg+xml",
        "generated image endpoint did not return SVG",
    )
    studio_support.require(
        svg_text.startswith("<svg "), "generated image body is not an SVG document"
    )
    try:
        svg = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as error:
        raise studio_support.StudioE2EError(
            "generated image body is malformed SVG"
        ) from error
    rendered_prompt = " ".join(
        element.text or ""
        for element in svg.findall(
            "{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}text"
        )
    )
    studio_support.require(
        rendered_prompt == INPUT_TEXT,
        "generated SVG lost or changed the requested prompt",
    )
    studio_support.require(bool(service_version), "AI Chat service version is missing")
    return TurnExpectations(
        service_version=service_version,
        workflow_run_id=workflow_run_id,
        agent_run_id=agent_run_id,
        turn_id=turn_id,
        user_message=copy.deepcopy(user),
        assistant_message=copy.deepcopy(assistant),
        image_id=image_id,
    )


def execute_fastapi_turn(
    *,
    api_key: str,
    ingestion_host: str,
    ingestion_port: int,
) -> TurnExpectations:
    """Exercise the real FastAPI route, SQLite store, demo driver, and lifespan."""

    from fastapi.testclient import TestClient

    from ai_chat import __version__
    from ai_chat.api.app import create_app
    from ai_chat.bootstrap import build_application
    from ai_chat.config import Settings, TelemetrySettings

    with tempfile.TemporaryDirectory(prefix="junjo-ai-chat-e2e-") as directory:
        data_directory = Path(directory)
        telemetry = TelemetrySettings(
            api_key=api_key,
            host=ingestion_host,
            port=ingestion_port,
            insecure=True,
        )
        application = build_application(
            Settings(
                database_path=data_directory / "chat.sqlite3",
                image_directory=data_directory / "images",
                cors_origins=(),
                telemetry=telemetry,
            )
        )
        app = create_app(application=application, telemetry=telemetry)
        with TestClient(app, base_url="http://ai-chat-e2e") as client:
            turn_response = client.post(
                f"/api/conversations/{CONVERSATION_ID}/turns",
                json={"text": INPUT_TEXT},
            )
            studio_support.require(
                turn_response.status_code == 200,
                "AI Chat turn request did not return HTTP 200",
            )
            messages_response = client.get(
                f"/api/conversations/{CONVERSATION_ID}/messages"
            )
            studio_support.require(
                messages_response.status_code == 200,
                "AI Chat persistence request did not return HTTP 200",
            )
            turn_payload = turn_response.json()
            assistant = _object(
                _object(turn_payload, "turn response").get("assistant_message"),
                "assistant message",
            )
            image_url = _nonempty_text(
                assistant.get("image_url"), "assistant image URL"
            )
            image_response = client.get(image_url)
            expectations = assert_http_turn(
                turn_payload=turn_payload,
                persistence_payload=messages_response.json(),
                svg_status=image_response.status_code,
                svg_content_type=image_response.headers.get("content-type", ""),
                svg_text=image_response.text,
                service_version=__version__,
            )
        # Exiting TestClient is part of the proof: it closes application state,
        # force-flushes the lifespan-owned provider, and shuts the exporter down.
        return expectations


def _assert_integrity(value: object, description: str) -> None:
    integrity = _object(value, f"{description} integrity")
    studio_support.require(
        integrity.get("status") == "complete", f"{description} evidence is incomplete"
    )
    studio_support.require(
        integrity.get("diagnostics") == [], f"{description} has evidence diagnostics"
    )
    loss_counts = _object(integrity.get("loss_counts"), f"{description} loss counts")
    studio_support.require(
        bool(loss_counts), f"{description} loss counters are missing"
    )
    studio_support.require(
        all(
            isinstance(count, int) and not isinstance(count, bool) and count == 0
            for count in loss_counts.values()
        ),
        f"{description} has OTLP evidence loss",
    )


def _replay_store(
    value: object,
    *,
    expected_actions: Sequence[str] | None,
    expected_transition_count: int,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    store = _object(value, "Store detail")
    start = _object(
        studio_support.assert_full_payload(store.get("start"), "Store start"),
        "Store start value",
    )
    end = _object(
        studio_support.assert_full_payload(store.get("end"), "Store end"),
        "Store end value",
    )
    studio_support.assert_verified_store(
        store,
        expected_start=start,
        expected_end=end,
        expected_actions=expected_actions,
        apply_patch=apply_patch,
    )
    studio_support.require(
        store.get("transition_count") == expected_transition_count,
        "Store transition count is incorrect",
    )
    store_id = _nonempty_text(store.get("store_id"), "Store ID")
    return start, end, store_id


def _agent_state(expectations: TurnExpectations, *, final: bool) -> dict[str, object]:
    transcript: list[dict[str, object]] = [
        {"type": "agent_input", "input": expectations.agent_input},
    ]
    if final:
        transcript.extend(
            [
                {
                    "type": "assistant_tool_calls",
                    "calls": [
                        {
                            "id": "image-1",
                            "name": "create_image",
                            "arguments": {"prompt": INPUT_TEXT},
                        }
                    ],
                },
                {
                    "type": "tool_result",
                    "callId": "image-1",
                    "toolName": "create_image",
                    "result": {"artifact": expectations.artifact},
                },
                {"type": "assistant_output", "output": expectations.agent_output},
            ]
        )
    return {
        "input": expectations.agent_input,
        "history": [],
        "transcript": transcript,
        "model_iteration": 2 if final else 0,
        "model_request_count": 2 if final else 0,
        "tool_call_requested_count": 1 if final else 0,
        "tool_call_admitted_count": 1 if final else 0,
        "tool_call_started_count": 1 if final else 0,
        "tool_call_completed_count": 1 if final else 0,
        "usage": {"v": 1, "modelResponses": 2 if final else 0, "fields": {}},
        "admitted_tool_call_ids": ["image-1"] if final else [],
        "pending_tool_call_ids": [],
        "completed_tool_call_ids": ["image-1"] if final else [],
        "final_output_available": final,
        "final_output": expectations.agent_output if final else None,
        "terminal_reason": "final_output" if final else None,
    }


def assert_agent_projection(
    *,
    summary_value: object,
    detail_value: object,
    expectations: TurnExpectations,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> tuple[SemanticIdentities, str]:
    """Validate exact Agent semantics and independently replay its Store."""

    summary = _object(summary_value, "Agent summary")
    detail = _object(detail_value, "Agent detail")
    studio_support.require(
        detail.get("summary") == summary, "Agent list/detail summaries diverged"
    )
    studio_support.require(
        summary.get("service")
        == {
            "namespace": SERVICE_NAMESPACE,
            "name": SERVICE_NAME,
            "version": expectations.service_version,
        },
        "Agent service identity is incorrect",
    )
    studio_support.require(
        summary.get("agent_key") == AGENT_KEY, "Agent key is incorrect"
    )
    studio_support.require(
        summary.get("agent_name") == AGENT_NAME, "Agent name is incorrect"
    )
    studio_support.require(
        summary.get("runtime_id") == expectations.agent_run_id,
        "Agent runtime ID is incorrect",
    )
    studio_support.require(
        summary.get("outcome") == "completed", "Agent did not complete"
    )
    studio_support.require(
        summary.get("termination_reason") == "final_output",
        "Agent termination is incorrect",
    )
    studio_support.require(
        summary.get("limits") == {"model_requests": 4, "tool_calls": 4},
        "Agent limits are incorrect",
    )
    studio_support.require(
        summary.get("counts")
        == {
            "operations": 3,
            "model_requests": 2,
            "tool_calls": {"requested": 1, "admitted": 1, "started": 1, "completed": 1},
        },
        "Agent operation counts are incorrect",
    )
    studio_support.require(
        summary.get("usage") == {"model_responses": 2, "fields": {}},
        "provider-free Agent usage is incorrect",
    )
    _assert_integrity(detail.get("integrity"), "Agent")
    studio_support.require(
        detail.get("error") is None, "completed Agent contains an error"
    )
    studio_support.require(
        detail.get("cancellation") is None, "completed Agent contains cancellation"
    )
    studio_support.assert_full_payload(detail.get("definition"), "Agent definition")
    studio_support.require(
        studio_support.assert_full_payload(detail.get("input"), "Agent input")
        == expectations.agent_input,
        "Agent input evidence is incorrect",
    )
    studio_support.require(
        studio_support.assert_full_payload(detail.get("output"), "Agent output")
        == expectations.agent_output,
        "Agent output evidence is incorrect",
    )

    operations = _list(detail.get("operations"), "Agent operations")
    studio_support.require(
        [operation.get("operation_type") for operation in operations]
        == ["model_request", "tool", "model_request"],
        "Agent operation types are not in realized order",
    )
    studio_support.require(
        [operation.get("sequence") for operation in operations] == [1, 2, 3],
        "Agent operation sequence is not contiguous",
    )
    first_model, tool, second_model = (
        _object(item, "Agent operation") for item in operations
    )
    for ordinal, model in enumerate((first_model, second_model), start=1):
        studio_support.require(
            model.get("ordinal") == ordinal, "model request ordinal is incorrect"
        )
        studio_support.require(
            model.get("outcome") == "completed", "model request did not complete"
        )
        studio_support.require(
            model.get("driver_key") == "ai_chat_demo", "model driver key is incorrect"
        )
        studio_support.require(
            model.get("provider") == "junjo", "model provider is incorrect"
        )
        studio_support.require(
            model.get("model_name") == "deterministic-demo-v1",
            "model name is incorrect",
        )
        studio_support.assert_full_payload(
            model.get("request"), f"model request {ordinal}"
        )
        candidate = _object(
            model.get("response_candidate"), f"model response candidate {ordinal}"
        )
        studio_support.require(
            candidate.get("available") is True,
            "model response candidate is unavailable",
        )
        studio_support.assert_full_payload(
            candidate.get("payload"), f"model response candidate {ordinal} payload"
        )
        studio_support.assert_full_payload(
            model.get("response"), f"model response {ordinal}"
        )
    studio_support.require(
        first_model.get("response_type") == "tool_calls",
        "first model response type is incorrect",
    )
    studio_support.require(
        second_model.get("response_type") == "final_output",
        "second model response type is incorrect",
    )
    studio_support.require(
        first_model.get("requested_tool_calls")
        == [
            {
                "call_id": "image-1",
                "ordinal": 1,
                "tool_name": "create_image",
                "observed_tool_operation": True,
                "admission": "admitted",
                "reason": None,
            }
        ],
        "requested Tool-call projection is incorrect",
    )
    studio_support.require(
        tool.get("call_id") == "image-1", "Tool call ID is incorrect"
    )
    studio_support.require(tool.get("ordinal") == 1, "Tool ordinal is incorrect")
    studio_support.require(
        tool.get("tool_name") == "create_image", "Tool name is incorrect"
    )
    studio_support.require(tool.get("outcome") == "completed", "Tool did not complete")
    studio_support.require(
        studio_support.assert_full_payload(
            tool.get("requested_arguments"), "Tool requested arguments"
        )
        == {"prompt": INPUT_TEXT},
        "Tool requested arguments are incorrect",
    )
    studio_support.require(
        studio_support.assert_full_payload(
            tool.get("arguments"), "Tool validated arguments"
        )
        == {"prompt": INPUT_TEXT},
        "Tool validated arguments are incorrect",
    )
    candidate = _object(tool.get("result_candidate"), "Tool result candidate")
    studio_support.require(
        candidate.get("available") is True, "Tool result candidate is unavailable"
    )
    studio_support.require(
        studio_support.assert_full_payload(
            candidate.get("payload"), "Tool result candidate payload"
        )
        == {"artifact": expectations.artifact},
        "Tool result candidate is incorrect",
    )
    studio_support.require(
        studio_support.assert_full_payload(tool.get("result"), "Tool result")
        == {"artifact": expectations.artifact},
        "Tool result is incorrect",
    )

    state_start, state_end, agent_store_id = _replay_store(
        detail.get("state"),
        expected_actions=None,
        expected_transition_count=8,
        apply_patch=apply_patch,
    )
    studio_support.require(
        state_start == _agent_state(expectations, final=False),
        "Agent Store start is incorrect",
    )
    studio_support.require(
        state_end == _agent_state(expectations, final=True),
        "Agent Store end is incorrect",
    )

    parent = _object(detail.get("parent_executable"), "Agent parent executable")
    studio_support.require(
        parent.get("executable_type") == "node", "Agent semantic parent is not a Node"
    )
    studio_support.require(
        parent.get("name") == "ExecuteAgentNode",
        "Agent semantic parent name is incorrect",
    )
    trace_id = _nonempty_text(summary.get("trace_id"), "Agent trace ID")
    agent_span_id = _nonempty_text(summary.get("agent_span_id"), "Agent span ID")
    execute_agent_span_id = _nonempty_text(
        parent.get("span_id"), "ExecuteAgent Node span ID"
    )
    studio_support.require(
        parent.get("trace_id") == trace_id, "Agent semantic parent left its trace"
    )
    studio_support.require(
        parent.get("physical_parent_span_id") == execute_agent_span_id,
        "Agent physical parent does not match its semantic Node parent",
    )

    nested_values = _list(detail.get("nested_executables"), "Agent nested executables")
    studio_support.require(
        len(nested_values) == 1, "Agent must expose exactly one nested image Workflow"
    )
    nested = _object(nested_values[0], "nested image Workflow")
    studio_support.require(
        nested.get("executable_type") == "workflow",
        "nested executable is not a Workflow",
    )
    studio_support.require(
        nested.get("name") == IMAGE_WORKFLOW_NAME, "nested Workflow name is incorrect"
    )
    studio_support.require(
        nested.get("parent_operation_sequence") == 2,
        "nested Workflow operation link is incorrect",
    )
    tool_span_id = _nonempty_text(tool.get("span_id"), "Tool span ID")
    studio_support.require(
        nested.get("parent_operation_span_id") == tool_span_id,
        "nested Workflow does not link to its physical Tool parent",
    )
    studio_support.require(
        nested.get("trace_id") == trace_id, "nested Workflow left its Agent trace"
    )
    nested_span_id = _nonempty_text(nested.get("span_id"), "nested Workflow span ID")
    return (
        SemanticIdentities(
            trace_id=trace_id,
            agent_span_id=agent_span_id,
            tool_span_id=tool_span_id,
            nested_workflow_span_id=nested_span_id,
            execute_agent_span_id=execute_agent_span_id,
        ),
        agent_store_id,
    )


def _state_message(
    message: Mapping[str, object], *, image_id: str | None
) -> dict[str, object]:
    image = None
    if image_id is not None:
        image = {
            "id": image_id,
            "url": message["image_url"],
            "alt_text": message["image_alt"],
        }
    return {
        "id": message["id"],
        "turn_id": message["turn_id"],
        "conversation_id": CONVERSATION_ID,
        "role": message["role"],
        "content": message["content"],
        "image": image,
        "created_at": message["created_at"],
    }


def _outer_states(
    expectations: TurnExpectations,
) -> tuple[dict[str, object], dict[str, object]]:
    start: dict[str, object] = {
        "conversation_id": CONVERSATION_ID,
        "turn_id": expectations.turn_id,
        "text": INPUT_TEXT,
        "user_message": None,
        "agent_output": None,
        "agent_run_id": None,
        "assistant_message": None,
    }
    end = {
        **start,
        "user_message": _state_message(expectations.user_message, image_id=None),
        "agent_output": expectations.agent_output,
        "agent_run_id": expectations.agent_run_id,
        "assistant_message": _state_message(
            expectations.assistant_message, image_id=expectations.image_id
        ),
    }
    return start, end


def _image_states(
    expectations: TurnExpectations,
) -> tuple[dict[str, object], dict[str, object]]:
    start: dict[str, object] = {
        "prompt": INPUT_TEXT,
        "prepared_prompt": None,
        "alt_text": None,
        "artifact": None,
    }
    return start, {
        **start,
        "prepared_prompt": INPUT_TEXT,
        "alt_text": IMAGE_ALT,
        "artifact": expectations.artifact,
    }


def assert_workflow_projection(
    value: object,
    *,
    trace_id: str,
    span_id: str,
    name: str,
    expected_states: tuple[dict[str, object], dict[str, object]],
    expected_actions: Sequence[str],
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> str:
    """Validate one backend-authoritative Workflow Store projection."""

    projection = _object(value, f"{name} diagnostic")
    studio_support.require(
        projection.get("trace_id") == trace_id, f"{name} trace ID is incorrect"
    )
    studio_support.require(
        projection.get("workflow_span_id") == span_id, f"{name} span ID is incorrect"
    )
    studio_support.require(
        projection.get("executable_type") == "workflow", f"{name} type is incorrect"
    )
    studio_support.require(projection.get("name") == name, f"{name} name is incorrect")
    _assert_integrity(projection.get("integrity"), name)
    start, end, store_id = _replay_store(
        projection.get("state"),
        expected_actions=expected_actions,
        expected_transition_count=len(expected_actions),
        apply_patch=apply_patch,
    )
    expected_start, expected_end = expected_states
    studio_support.require(start == expected_start, f"{name} Store start is incorrect")
    studio_support.require(end == expected_end, f"{name} Store end is incorrect")
    return store_id


def _attributes(span: Mapping[str, object], description: str) -> dict[str, Any]:
    return _object(span.get("attributes_json"), f"{description} attributes")


def _one_span(
    spans: Sequence[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    description: str,
) -> dict[str, Any]:
    matches = [span for span in spans if predicate(span)]
    studio_support.require(
        len(matches) == 1, f"trace must contain exactly one {description}"
    )
    return matches[0]


def assert_raw_hierarchy(
    raw_value: object,
    *,
    identities: SemanticIdentities,
    expectations: TurnExpectations,
) -> tuple[str, str]:
    """Prove the exact eleven-span physical tree and semantic ownership."""

    raw_spans = _list(raw_value, "raw trace spans")
    studio_support.require(
        len(raw_spans) == EXPECTED_SPAN_COUNT,
        "AI Chat trace must contain exactly eleven spans",
    )
    spans = [
        _object(value, f"raw span {index}") for index, value in enumerate(raw_spans)
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for index, span in enumerate(spans):
        span_id = _nonempty_text(span.get("span_id"), f"raw span {index} ID")
        studio_support.require(span_id not in by_id, "raw span IDs must be unique")
        by_id[span_id] = span
        studio_support.require(
            span.get("trace_id") == identities.trace_id,
            "raw span left the expected trace",
        )
        studio_support.require(
            span.get("service_name") == SERVICE_NAME, "raw service name is incorrect"
        )
        resource = _object(span.get("resource_attributes_json"), "raw span resource")
        studio_support.require(
            resource.get("service.namespace") == SERVICE_NAMESPACE,
            "raw namespace is incorrect",
        )
        studio_support.require(
            resource.get("service.name") == SERVICE_NAME,
            "raw resource service name is incorrect",
        )
        studio_support.require(
            resource.get("service.version") == expectations.service_version,
            "raw service version is incorrect",
        )
        for field in (
            "dropped_attributes_count",
            "dropped_events_count",
            "dropped_links_count",
            "resource_dropped_attributes_count",
        ):
            studio_support.require(
                span.get(field) == 0, f"raw span has evidence loss in {field}"
            )
        for event_index, event_value in enumerate(
            _list(span.get("events_json"), "raw span events")
        ):
            event = _object(event_value, f"raw span event {event_index}")
            studio_support.require(
                event.get("droppedAttributesCount") == 0, "raw event dropped attributes"
            )

    outer = _one_span(
        spans,
        lambda span: (
            _attributes(span, "span").get("junjo.span_type") == "workflow"
            and _attributes(span, "span").get("junjo.executable_runtime_id")
            == expectations.workflow_run_id
        ),
        "outer Chat Turn Workflow",
    )
    agent = by_id.get(identities.agent_span_id)
    nested = by_id.get(identities.nested_workflow_span_id)
    tool = by_id.get(identities.tool_span_id)
    execute_agent = by_id.get(identities.execute_agent_span_id)
    studio_support.require(
        all(value is not None for value in (agent, nested, tool, execute_agent)),
        "semantic spans are absent",
    )
    assert (
        agent is not None
        and nested is not None
        and tool is not None
        and execute_agent is not None
    )
    outer_span_id = _nonempty_text(outer.get("span_id"), "outer Workflow span ID")
    studio_support.require(
        outer.get("parent_span_id") in {None, ""},
        "outer Workflow must be the physical root",
    )
    studio_support.require(
        outer.get("name") == OUTER_WORKFLOW_NAME, "outer Workflow name is incorrect"
    )

    nodes = {
        name: _one_span(
            spans, lambda span, name=name: span.get("name") == name, f"{name} span"
        )
        for name in (
            "PersistInputNode",
            "ExecuteAgentNode",
            "PersistResultNode",
            "PrepareImagePromptNode",
            "RenderImageNode",
        )
    }
    studio_support.require(
        nodes["ExecuteAgentNode"].get("span_id") == identities.execute_agent_span_id,
        "Node identity drifted",
    )
    for name in ("PersistInputNode", "ExecuteAgentNode", "PersistResultNode"):
        studio_support.require(
            nodes[name].get("parent_span_id") == outer_span_id,
            f"{name} is not an outer child",
        )
    studio_support.require(
        agent.get("parent_span_id") == identities.execute_agent_span_id,
        "Agent is not an ExecuteAgent child",
    )

    agent_attributes = _attributes(agent, "Agent")
    execute_attributes = _attributes(execute_agent, "ExecuteAgentNode")
    studio_support.require(
        agent_attributes.get("junjo.span_type") == "agent",
        "raw Agent type is incorrect",
    )
    studio_support.require(
        agent_attributes.get("junjo.executable_runtime_id")
        == expectations.agent_run_id,
        "raw Agent run is incorrect",
    )
    studio_support.require(
        agent_attributes.get("junjo.parent_executable_type") == "node",
        "raw Agent parent type is incorrect",
    )
    for suffix in ("definition_id", "runtime_id", "structural_id"):
        studio_support.require(
            agent_attributes.get(f"junjo.parent_executable_{suffix}")
            == execute_attributes.get(f"junjo.executable_{suffix}"),
            f"raw Agent semantic parent {suffix} is incorrect",
        )

    operations = [
        span
        for span in spans
        if _attributes(span, "span").get("junjo.agent.operation_type")
        in {"model_request", "tool"}
    ]
    studio_support.require(
        len(operations) == 3, "raw trace must contain three Agent operations"
    )
    operations.sort(
        key=lambda span: _attributes(span, "operation").get(
            "junjo.agent.operation.sequence", 0
        )
    )
    studio_support.require(
        [
            _attributes(span, "operation").get("junjo.agent.operation.sequence")
            for span in operations
        ]
        == [1, 2, 3],
        "raw operation sequence is incorrect",
    )
    studio_support.require(
        [
            _attributes(span, "operation").get("junjo.agent.operation_type")
            for span in operations
        ]
        == ["model_request", "tool", "model_request"],
        "raw operation types are incorrect",
    )
    studio_support.require(
        all(
            span.get("parent_span_id") == identities.agent_span_id
            for span in operations
        ),
        "raw operations are not direct Agent children",
    )
    studio_support.require(
        operations[1].get("span_id") == identities.tool_span_id,
        "raw Tool identity is incorrect",
    )

    studio_support.require(
        nested.get("parent_span_id") == identities.tool_span_id,
        "nested Workflow is not a Tool child",
    )
    studio_support.require(
        nested.get("name") == IMAGE_WORKFLOW_NAME,
        "raw nested Workflow name is incorrect",
    )
    nested_attributes = _attributes(nested, "nested Workflow")
    studio_support.require(
        nested_attributes.get("junjo.span_type") == "workflow",
        "raw nested type is incorrect",
    )
    studio_support.require(
        nested_attributes.get("junjo.parent_executable_type") == "agent",
        "nested semantic parent is incorrect",
    )
    for suffix in ("definition_id", "runtime_id", "structural_id"):
        studio_support.require(
            nested_attributes.get(f"junjo.parent_executable_{suffix}")
            == agent_attributes.get(f"junjo.executable_{suffix}"),
            f"nested Workflow semantic Agent parent {suffix} is incorrect",
        )
    for name in ("PrepareImagePromptNode", "RenderImageNode"):
        studio_support.require(
            nodes[name].get("parent_span_id") == identities.nested_workflow_span_id,
            f"{name} is not a nested Workflow child",
        )

    actual_edges = {
        (_nonempty_text(span.get("parent_span_id"), "raw parent span ID"), span_id)
        for span_id, span in by_id.items()
        if span.get("parent_span_id") not in {None, ""}
    }
    studio_support.require(
        len(actual_edges) == EXPECTED_SPAN_COUNT - 1,
        "raw hierarchy is not one connected tree",
    )
    nested_runtime_id = _nonempty_text(
        nested_attributes.get("junjo.executable_runtime_id"),
        "nested Workflow runtime ID",
    )
    return outer_span_id, nested_runtime_id


def fetch_agent_projection(
    client: studio_support.JsonClient,
    *,
    expectations: TurnExpectations,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Poll until Studio exposes the exact Agent emitted by the HTTP turn."""

    query = urllib.parse.urlencode(
        {
            "service_namespace": SERVICE_NAMESPACE,
            "service_name": SERVICE_NAME,
            "agent_key": AGENT_KEY,
            "limit": 100,
        }
    )

    def query_projection() -> tuple[dict[str, Any], dict[str, Any]] | None:
        summaries = _list(
            client.request(f"/api/v1/agent-executions?{query}"), "Agent execution list"
        )
        matches = [
            summary
            for summary in summaries
            if isinstance(summary, dict)
            and summary.get("runtime_id") == expectations.agent_run_id
        ]
        if not matches:
            return None
        studio_support.require(
            len(matches) == 1, "Studio returned duplicate Agent runtime identities"
        )
        summary = matches[0]
        trace_id = _nonempty_text(summary.get("trace_id"), "Agent trace ID")
        span_id = _nonempty_text(summary.get("agent_span_id"), "Agent span ID")
        detail = _object(
            client.request(f"/api/v1/agent-executions/{trace_id}/{span_id}"),
            "Agent execution detail",
        )
        return summary, detail

    result = studio_support.bounded_poll(
        query_projection,
        accept=lambda value: value is not None,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description="the AI Chat Agent semantic projection",
    )
    studio_support.require(
        result is not None, "AI Chat Agent semantic projection is absent"
    )
    return result


def run(args: argparse.Namespace) -> None:
    """Execute the authenticated live application-to-Studio proof."""

    import jsonpatch

    studio = studio_support.JsonClient(args.backend_url)
    studio_support.wait_for_health(
        studio,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.poll_interval_seconds,
    )
    identity: studio_support.TestIdentity | None = None
    evidence: dict[str, object] | None = None
    primary_error: BaseException | None = None
    try:
        identity = studio_support.provision_test_identity(studio)
        expectations = execute_fastapi_turn(
            api_key=identity.api_key,
            ingestion_host=args.ingestion_host,
            ingestion_port=args.ingestion_port,
        )
        summary, detail = fetch_agent_projection(
            studio,
            expectations=expectations,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )

        def apply_patch(document: object, patch: list[dict[str, object]]) -> object:
            return jsonpatch.JsonPatch(patch).apply(document, in_place=False)

        identities, agent_store_id = assert_agent_projection(
            summary_value=summary,
            detail_value=detail,
            expectations=expectations,
            apply_patch=apply_patch,
        )
        raw_spans = studio_support.bounded_poll(
            lambda: studio.request(
                f"/api/v1/observability/traces/{identities.trace_id}/spans"
            ),
            accept=lambda value: (
                isinstance(value, list) and len(value) == EXPECTED_SPAN_COUNT
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
            description="all eleven AI Chat OTLP spans",
        )
        outer_span_id, _ = assert_raw_hierarchy(
            raw_spans,
            identities=identities,
            expectations=expectations,
        )
        outer_projection = studio_support.bounded_poll(
            lambda: studio.request(
                f"/api/v1/workflow-executions/{identities.trace_id}/{outer_span_id}/store"
            ),
            accept=lambda value: isinstance(value, dict),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
            description="the outer Chat Turn Workflow Store projection",
        )
        nested_projection = studio_support.bounded_poll(
            lambda: studio.request(
                f"/api/v1/workflow-executions/{identities.trace_id}/"
                f"{identities.nested_workflow_span_id}/store"
            ),
            accept=lambda value: isinstance(value, dict),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
            description="the nested image Workflow Store projection",
        )
        outer_store_id = assert_workflow_projection(
            outer_projection,
            trace_id=identities.trace_id,
            span_id=outer_span_id,
            name=OUTER_WORKFLOW_NAME,
            expected_states=_outer_states(expectations),
            expected_actions=[
                "set_user_message",
                "set_agent_result",
                "set_assistant_message",
            ],
            apply_patch=apply_patch,
        )
        nested_store_id = assert_workflow_projection(
            nested_projection,
            trace_id=identities.trace_id,
            span_id=identities.nested_workflow_span_id,
            name=IMAGE_WORKFLOW_NAME,
            expected_states=_image_states(expectations),
            expected_actions=["set_prepared_prompt", "set_artifact"],
            apply_patch=apply_patch,
        )
        studio_support.require(
            len({outer_store_id, agent_store_id, nested_store_id}) == 3,
            "outer Workflow, Agent, and nested Workflow must own independent Stores",
        )
        evidence = build_live_evidence(
            expectations=expectations,
            identities=identities,
            outer_span_id=outer_span_id,
        )
    except BaseException as error:
        primary_error = error

    cleanup_error: BaseException | None = None
    if identity is not None:
        try:
            studio_support.cleanup_test_identity(studio, identity)
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
    studio_support.require(evidence is not None, "live evidence was not produced")
    write_live_evidence(args.evidence_output, evidence)
    print(
        "AI Chat Studio E2E passed: FastAPI response and SQLite persistence, "
        "eleven-span OTLP hierarchy, semantic parentage, and three independent "
        "verified Store replays are complete.",
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
        required=True,
        help="Credential-free JSON evidence written only after complete success.",
    )
    return parser


def main() -> int:
    """Validate arguments and run the live proof."""

    args = build_parser().parse_args()
    studio_support.require(
        0 < args.ingestion_port <= 65_535, "--ingestion-port is invalid"
    )
    studio_support.require(
        bool(args.ingestion_host.strip()), "--ingestion-host cannot be empty"
    )
    studio_support.require(
        args.timeout_seconds > 0, "--timeout-seconds must be positive"
    )
    studio_support.require(
        args.poll_interval_seconds > 0, "--poll-interval-seconds must be positive"
    )
    run(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except studio_support.StudioE2EError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
