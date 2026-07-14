#!/usr/bin/env python3
"""Prove the restored AI Chat -> Junjo -> OTLP -> Studio path live.

The proof starts at the FastAPI boundary. It admits one server-owned Turn,
polls the asynchronous Turn resource to completion, reloads the canonical JSON
from a fresh SQLite application, and validates the generated image. It then
queries one authenticated Studio ``TraceEvidence`` document and proves the
restored deterministic Workflow shell, bounded Agent branch, Agent Tool to
nested Workflow composition, three independently replayable Stores, exact
runtime-ID resolution, and the Studio browser diagnostics path.

Run from the repository root after syncing the AI Chat workspace package:

    uv run --project sdks/python --package junjo-ai-chat-example \
        python tooling/scripts/validate_ai_chat_studio_e2e.py \
        --evidence-output /tmp/junjo-ai-chat-evidence.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
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
INPUT_TEXT = "Create a visual of a telemetry lighthouse"
ASSISTANT_TEXT = "I created the requested deterministic illustration."
IMAGE_ALT = f"Deterministic illustration: {INPUT_TEXT}"
EXPECTED_SPAN_COUNT = 14
FULL_POLICY = studio_support.FULL_POLICY
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

RAW_SPAN_FIELDS = {
    "trace_id",
    "span_id",
    "parent_span_id",
    "service_name",
    "name",
    "kind",
    "start_time",
    "end_time",
    "status_code",
    "status_message",
    "attributes_json",
    "events_json",
    "links_json",
    "trace_flags",
    "trace_state",
    "dropped_attributes_count",
    "dropped_events_count",
    "dropped_links_count",
    "resource_attributes_json",
    "resource_dropped_attributes_count",
}


@dataclass(frozen=True, slots=True)
class TurnExpectations:
    """Detached application facts used to identify one live execution."""

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
    """Stable identities discovered in one cohesive TraceEvidence document."""

    trace_id: str
    outer_workflow_span_id: str
    agent_span_id: str
    general_response_span_id: str
    tool_span_id: str
    nested_workflow_span_id: str
    nested_workflow_runtime_id: str


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
    studio_support.require(set(value) == expected, f"{description} fields are incorrect")


def _assert_utc_timestamp(value: object, description: str) -> None:
    text = _nonempty_text(value, description)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise studio_support.StudioE2EError(
            f"{description} is not ISO 8601"
        ) from error
    studio_support.require(
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.utcoffset().total_seconds() == 0,
        f"{description} must identify UTC",
    )


def assert_http_turn(
    *,
    admitted_payload: object,
    terminal_payload: object,
    persistence_payload: object,
    svg_status: int,
    svg_content_type: str,
    svg_text: str,
    service_version: str,
) -> TurnExpectations:
    """Validate admission, terminal polling, fresh reload, and image ownership."""

    admitted = _object(admitted_payload, "admitted Turn response")
    terminal = _object(terminal_payload, "terminal Turn response")
    expected_turn_keys = {
        "object_type",
        "schema_version",
        "id",
        "revision",
        "conversation_id",
        "sequence",
        "status",
        "context_policy",
        "user_message",
        "assistant_message",
        "execution_references",
        "failure",
        "created_at",
        "updated_at",
        "completed_at",
    }
    _exact_keys(admitted, expected_turn_keys, "admitted Turn response")
    _exact_keys(terminal, expected_turn_keys, "terminal Turn response")
    turn_id = _nonempty_text(admitted.get("id"), "Turn ID")
    studio_support.require(terminal.get("id") == turn_id, "Turn identity changed")
    studio_support.require(
        admitted.get("object_type") == "ai_chat.turn"
        and admitted.get("schema_version") == 1,
        "admitted Turn type or schema is incorrect",
    )
    studio_support.require(
        admitted.get("revision") == 0 and admitted.get("status") == "admitted",
        "POST did not return the durably admitted Turn",
    )
    studio_support.require(
        admitted.get("assistant_message") is None
        and admitted.get("failure") is None
        and admitted.get("completed_at") is None,
        "admitted Turn contains terminal evidence",
    )
    studio_support.require(
        admitted.get("execution_references")
        == {"workflow_run_id": None, "agent_run_id": None},
        "admitted Turn contains execution identities",
    )
    studio_support.require(
        terminal.get("revision") == 3 and terminal.get("status") == "completed",
        "polled Turn did not complete through the expected lifecycle",
    )
    studio_support.require(
        terminal.get("conversation_id") == CONVERSATION_ID
        and terminal.get("sequence") == 1,
        "terminal Turn conversation ordering is incorrect",
    )
    studio_support.require(
        terminal.get("context_policy")
        == {"id": "recent-completed-turns", "version": 1, "recent_turn_limit": 8},
        "Turn context policy is incorrect",
    )
    studio_support.require(
        terminal.get("failure") is None, "completed Turn contains failure evidence"
    )
    references = _object(terminal.get("execution_references"), "execution references")
    workflow_run_id = _nonempty_text(
        references.get("workflow_run_id"), "Workflow run ID"
    )
    agent_run_id = _nonempty_text(references.get("agent_run_id"), "Agent run ID")
    studio_support.require(
        workflow_run_id != agent_run_id,
        "Workflow and Agent runtime identities must be independent",
    )

    user = _object(terminal.get("user_message"), "user message")
    assistant = _object(terminal.get("assistant_message"), "assistant message")
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
    studio_support.require(
        user.get("turn_id") == turn_id and assistant.get("turn_id") == turn_id,
        "messages lost the authoritative Turn identity",
    )
    studio_support.require(
        user.get("role") == "user"
        and user.get("content") == INPUT_TEXT
        and user.get("image_url") is None
        and user.get("image_alt") is None,
        "user message projection is incorrect",
    )
    studio_support.require(
        assistant.get("role") == "assistant"
        and assistant.get("content") == ASSISTANT_TEXT
        and assistant.get("image_alt") == IMAGE_ALT,
        "assistant message projection is incorrect",
    )
    _assert_utc_timestamp(user.get("created_at"), "user message timestamp")
    _assert_utc_timestamp(assistant.get("created_at"), "assistant message timestamp")
    _assert_utc_timestamp(terminal.get("created_at"), "Turn creation timestamp")
    _assert_utc_timestamp(terminal.get("updated_at"), "Turn update timestamp")
    _assert_utc_timestamp(terminal.get("completed_at"), "Turn completion timestamp")

    image_url = _nonempty_text(assistant.get("image_url"), "assistant image URL")
    image_match = re.fullmatch(r"/api/images/([0-9a-f]{32})\.svg", image_url)
    studio_support.require(
        image_match is not None,
        "assistant image URL is not an application-owned deterministic artifact",
    )
    assert image_match is not None
    image_id = image_match.group(1)

    persisted = _object(persistence_payload, "Turn-list response")
    _exact_keys(persisted, {"conversation_id", "turns"}, "Turn-list response")
    studio_support.require(
        persisted.get("conversation_id") == CONVERSATION_ID
        and persisted.get("turns") == [terminal],
        "fresh application reload did not reproduce the canonical terminal Turn",
    )
    studio_support.require(
        svg_status == 200
        and svg_content_type.split(";", 1)[0].strip() == "image/svg+xml",
        "generated image endpoint did not return SVG",
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
    timeout_seconds: float,
    interval_seconds: float,
) -> TurnExpectations:
    """Exercise asynchronous admission, polling, SQLite reload, and OTLP flush."""

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
        settings = Settings(
            database_path=data_directory / "chat.sqlite3",
            image_directory=data_directory / "images",
            cors_origins=(),
            telemetry=telemetry,
        )
        application = build_application(settings)
        app = create_app(application=application, telemetry=telemetry)
        with TestClient(app, base_url="http://ai-chat-e2e") as client:
            response = client.post(
                f"/api/conversations/{CONVERSATION_ID}/turns",
                json={"text": INPUT_TEXT},
            )
            studio_support.require(
                response.status_code == 202,
                "AI Chat Turn admission did not return HTTP 202",
            )
            admitted_payload = response.json()
            turn_id = _nonempty_text(
                _object(admitted_payload, "admitted Turn").get("id"), "Turn ID"
            )

            def load_turn() -> object:
                turn_response = client.get(f"/api/turns/{turn_id}")
                studio_support.require(
                    turn_response.status_code == 200,
                    "AI Chat Turn polling did not return HTTP 200",
                )
                return turn_response.json()

            terminal_payload = studio_support.bounded_poll(
                load_turn,
                accept=lambda value: isinstance(value, dict)
                and value.get("status") in {"completed", "failed", "cancelled"},
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
                description="the admitted AI Chat Turn to become terminal",
            )
            assistant = _object(
                _object(terminal_payload, "terminal Turn").get("assistant_message"),
                "assistant message",
            )
            image_url = _nonempty_text(assistant.get("image_url"), "assistant image URL")
            image_response = client.get(image_url)
            svg_status = image_response.status_code
            svg_content_type = image_response.headers.get("content-type", "")
            svg_text = image_response.text

        reloaded_application = build_application(
            Settings(
                database_path=data_directory / "chat.sqlite3",
                image_directory=data_directory / "images",
                cors_origins=(),
                telemetry=None,
            )
        )
        reloaded_app = create_app(application=reloaded_application)
        with TestClient(reloaded_app, base_url="http://ai-chat-reload-e2e") as client:
            turns_response = client.get(f"/api/conversations/{CONVERSATION_ID}/turns")
            studio_support.require(
                turns_response.status_code == 200,
                "fresh AI Chat Turn reload did not return HTTP 200",
            )
            return assert_http_turn(
                admitted_payload=admitted_payload,
                terminal_payload=terminal_payload,
                persistence_payload=turns_response.json(),
                svg_status=svg_status,
                svg_content_type=svg_content_type,
                svg_text=svg_text,
                service_version=__version__,
            )


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


def _assert_integrity(value: object, description: str) -> None:
    integrity = _object(value, f"{description} integrity")
    studio_support.require(
        integrity.get("status") == "complete"
        and integrity.get("diagnostics") == [],
        f"{description} evidence is incomplete",
    )
    loss_counts = _object(integrity.get("loss_counts"), f"{description} loss counts")
    studio_support.require(
        bool(loss_counts)
        and all(
            isinstance(count, int) and not isinstance(count, bool) and count == 0
            for count in loss_counts.values()
        ),
        f"{description} has preserved OTLP evidence loss",
    )


def _assert_store(
    annotation_value: object,
    *,
    expected_owner_span_id: str,
    expected_owner_type: str,
    expected_actions: Sequence[str] | None,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    annotation = _object(annotation_value, "Store annotation")
    studio_support.require(
        annotation.get("owner_span_id") == expected_owner_span_id
        and annotation.get("owner_executable_type") == expected_owner_type,
        "Store annotation owner is incorrect",
    )
    _assert_integrity(annotation.get("integrity"), "Store")
    detail = _object(annotation.get("detail"), "Store detail")
    start = _object(
        studio_support.assert_full_payload(detail.get("start"), "Store start"),
        "Store start value",
    )
    end = _object(
        studio_support.assert_full_payload(detail.get("end"), "Store end"),
        "Store end value",
    )
    studio_support.assert_verified_store(
        detail,
        expected_start=start,
        expected_end=end,
        expected_actions=expected_actions,
        apply_patch=apply_patch,
    )
    return annotation, start, end


def assert_trace_evidence(
    value: object,
    *,
    expectations: TurnExpectations,
    apply_patch: Callable[[object, list[dict[str, object]]], object],
) -> SemanticIdentities:
    """Validate one lossless document across raw, Workflow, and Agent views."""

    evidence = _object(value, "TraceEvidence")
    _exact_keys(
        evidence,
        {
            "trace_id",
            "spans",
            "executables_by_span_id",
            "operations_by_owner_runtime_id",
            "stores_by_id",
            "relationships_by_owner_span_id",
            "diagnostics",
        },
        "TraceEvidence",
    )
    trace_id = _nonempty_text(evidence.get("trace_id"), "TraceEvidence trace ID")
    studio_support.require(
        evidence.get("diagnostics") == [], "complete live trace has diagnostics"
    )
    raw_spans = _list(evidence.get("spans"), "TraceEvidence spans")
    studio_support.require(
        len(raw_spans) == EXPECTED_SPAN_COUNT,
        f"AI Chat trace must contain exactly {EXPECTED_SPAN_COUNT} spans",
    )
    spans = [
        _object(raw, f"raw span {index}") for index, raw in enumerate(raw_spans)
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for index, span in enumerate(spans):
        _exact_keys(span, RAW_SPAN_FIELDS, f"raw span {index}")
        span_id = _nonempty_text(span.get("span_id"), f"raw span {index} ID")
        studio_support.require(span_id not in by_id, "raw span IDs must be unique")
        by_id[span_id] = span
        studio_support.require(
            span.get("trace_id") == trace_id
            and span.get("service_name") == SERVICE_NAME,
            "raw span left the expected trace or service",
        )
        resource = _object(span.get("resource_attributes_json"), "raw span resource")
        studio_support.require(
            resource.get("service.namespace") == SERVICE_NAMESPACE
            and resource.get("service.name") == SERVICE_NAME
            and resource.get("service.version") == expectations.service_version,
            "raw span resource identity is incorrect",
        )
        for field in (
            "dropped_attributes_count",
            "dropped_events_count",
            "dropped_links_count",
            "resource_dropped_attributes_count",
        ):
            studio_support.require(span.get(field) == 0, f"raw span lost {field}")
        for event_value in _list(span.get("events_json"), "raw span events"):
            event = _object(event_value, "raw span event")
            studio_support.require(
                event.get("droppedAttributesCount") == 0,
                "raw span event lost attributes",
            )
        attributes = _attributes(span, f"raw span {index}")
        if attributes.get("junjo.span_type") is not None:
            studio_support.require(
                attributes.get("junjo.correlation.type") == "ai_chat.turn"
                and attributes.get("junjo.correlation.id") == expectations.turn_id,
                "executable owner lost the authoritative Turn correlation",
            )
        else:
            studio_support.require(
                "junjo.correlation.type" not in attributes
                and "junjo.correlation.id" not in attributes,
                "operation span duplicated owner correlation",
            )

    outer = _one_span(
        spans,
        lambda span: _attributes(span, "span").get("junjo.executable_runtime_id")
        == expectations.workflow_run_id,
        "outer Chat Turn Workflow",
    )
    agent = _one_span(
        spans,
        lambda span: _attributes(span, "span").get("junjo.executable_runtime_id")
        == expectations.agent_run_id,
        "AI Chat Agent",
    )
    general = _one_span(
        spans,
        lambda span: span.get("name") == "CreateGeneralAgentResponseNode",
        "general Agent response Node",
    )
    tool = _one_span(
        spans,
        lambda span: _attributes(span, "span").get("junjo.agent.operation_type")
        == "tool",
        "Agent Tool operation",
    )
    nested = _one_span(
        spans,
        lambda span: span.get("name") == IMAGE_WORKFLOW_NAME,
        "nested image Workflow",
    )
    outer_span_id = _nonempty_text(outer.get("span_id"), "outer Workflow span ID")
    agent_span_id = _nonempty_text(agent.get("span_id"), "Agent span ID")
    general_span_id = _nonempty_text(general.get("span_id"), "general Node span ID")
    tool_span_id = _nonempty_text(tool.get("span_id"), "Tool span ID")
    nested_span_id = _nonempty_text(nested.get("span_id"), "nested Workflow span ID")
    nested_runtime_id = _nonempty_text(
        _attributes(nested, "nested Workflow").get("junjo.executable_runtime_id"),
        "nested Workflow runtime ID",
    )
    studio_support.require(
        outer.get("name") == OUTER_WORKFLOW_NAME
        and outer.get("parent_span_id") in {None, ""},
        "outer Workflow is not the physical root",
    )
    expected_parents = {
        "Load Turn Context": outer_span_id,
        "AssessMessageDirectiveNode": outer_span_id,
        "CreateGeneralAgentResponseNode": outer_span_id,
        "PersistOutcomeNode": outer_span_id,
        AGENT_NAME: general_span_id,
        IMAGE_WORKFLOW_NAME: tool_span_id,
        "PrepareImagePromptNode": nested_span_id,
        "RenderImageNode": nested_span_id,
    }
    for name, parent_id in expected_parents.items():
        span = _one_span(spans, lambda item, name=name: item.get("name") == name, name)
        studio_support.require(
            span.get("parent_span_id") == parent_id,
            f"{name} has the wrong physical parent",
        )
    context_span = _one_span(
        spans, lambda span: span.get("name") == "Load Turn Context", "context group"
    )
    context_span_id = _nonempty_text(context_span.get("span_id"), "context span ID")
    for name in ("LoadRecentContextNode", "LoadContactNode"):
        span = _one_span(spans, lambda item, name=name: item.get("name") == name, name)
        studio_support.require(
            span.get("parent_span_id") == context_span_id,
            f"{name} is not a concurrent context child",
        )

    operations = [
        span
        for span in spans
        if _attributes(span, "span").get("junjo.agent.operation_type")
        in {"model_request", "tool"}
    ]
    operations.sort(
        key=lambda span: _attributes(span, "operation").get(
            "junjo.agent.operation.sequence", 0
        )
    )
    studio_support.require(
        [
            _attributes(span, "operation").get("junjo.agent.operation_type")
            for span in operations
        ]
        == ["model_request", "tool", "model_request"],
        "Agent operation sequence is incorrect",
    )
    studio_support.require(
        all(span.get("parent_span_id") == agent_span_id for span in operations),
        "Agent operations are not direct Agent children",
    )
    actual_edges = {
        (_nonempty_text(span.get("parent_span_id"), "parent span ID"), span_id)
        for span_id, span in by_id.items()
        if span.get("parent_span_id") not in {None, ""}
    }
    studio_support.require(
        len(actual_edges) == EXPECTED_SPAN_COUNT - 1,
        "raw hierarchy is not one connected tree",
    )

    executables = _object(
        evidence.get("executables_by_span_id"), "executable annotations"
    )
    agent_annotation = _object(executables.get(agent_span_id), "Agent annotation")
    outer_annotation = _object(executables.get(outer_span_id), "outer Workflow annotation")
    nested_annotation = _object(
        executables.get(nested_span_id), "nested Workflow annotation"
    )
    studio_support.require(
        agent_annotation.get("executable_type") == "agent"
        and agent_annotation.get("runtime_id") == expectations.agent_run_id,
        "Agent annotation identity is incorrect",
    )
    summary = _object(agent_annotation.get("summary"), "Agent summary")
    studio_support.require(
        summary.get("trace_id") == trace_id
        and summary.get("agent_span_id") == agent_span_id
        and summary.get("agent_key") == AGENT_KEY
        and summary.get("agent_name") == AGENT_NAME
        and summary.get("outcome") == "completed"
        and summary.get("termination_reason") == "final_output",
        "Agent summary identity or outcome is incorrect",
    )
    studio_support.require(
        summary.get("limits") == {"model_requests": 4, "tool_calls": 4}
        and summary.get("counts")
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
        "Agent bounded-operation summary is incorrect",
    )
    _assert_integrity(agent_annotation.get("integrity"), "Agent")
    studio_support.require(
        studio_support.assert_full_payload(agent_annotation.get("input"), "Agent input")
        == expectations.agent_input
        and studio_support.assert_full_payload(
            agent_annotation.get("output"), "Agent output"
        )
        == expectations.agent_output,
        "Agent input or output evidence is incorrect",
    )

    operations_by_owner = _object(
        evidence.get("operations_by_owner_runtime_id"), "operation index"
    )
    indexed_operations = _object(
        operations_by_owner.get(expectations.agent_run_id), "Agent operation index"
    )
    ordered_operations = sorted(
        (_object(item, "Agent operation") for item in indexed_operations.values()),
        key=lambda item: item.get("sequence", 0),
    )
    studio_support.require(
        [item.get("operation_type") for item in ordered_operations]
        == ["model_request", "tool", "model_request"],
        "TraceEvidence Agent operation index is incorrect",
    )
    indexed_tool = ordered_operations[1]
    studio_support.require(
        indexed_tool.get("span_id") == tool_span_id
        and indexed_tool.get("tool_name") == "create_image"
        and studio_support.assert_full_payload(
            indexed_tool.get("arguments"), "Tool validated arguments"
        )
        == {"prompt": INPUT_TEXT}
        and studio_support.assert_full_payload(
            indexed_tool.get("result"), "Tool result"
        )
        == {"artifact": expectations.artifact},
        "Agent Tool evidence is incorrect",
    )

    relationships = _object(
        evidence.get("relationships_by_owner_span_id"), "relationship index"
    )
    agent_relationships = _object(
        relationships.get(agent_span_id), "Agent relationships"
    )
    parent = _object(agent_relationships.get("parent"), "Agent parent")
    nested_values = _list(agent_relationships.get("nested"), "Agent nested executions")
    studio_support.require(
        parent.get("executable_type") == "node"
        and parent.get("name") == "CreateGeneralAgentResponseNode"
        and parent.get("span_id") == general_span_id,
        "Agent semantic parent is incorrect",
    )
    studio_support.require(
        len(nested_values) == 1
        and nested_values[0].get("name") == IMAGE_WORKFLOW_NAME
        and nested_values[0].get("span_id") == nested_span_id
        and nested_values[0].get("parent_operation_span_id") == tool_span_id,
        "Agent nested Workflow relationship is incorrect",
    )

    store_ids = {
        _nonempty_text(agent_annotation.get("store_id"), "Agent Store ID"),
        _nonempty_text(outer_annotation.get("store_id"), "outer Workflow Store ID"),
        _nonempty_text(nested_annotation.get("store_id"), "nested Workflow Store ID"),
    }
    studio_support.require(
        len(store_ids) == 3, "each executable must own an independent Store"
    )
    stores = _object(evidence.get("stores_by_id"), "Store index")
    agent_store_id = _nonempty_text(agent_annotation.get("store_id"), "Agent Store ID")
    outer_store_id = _nonempty_text(
        outer_annotation.get("store_id"), "outer Workflow Store ID"
    )
    nested_store_id = _nonempty_text(
        nested_annotation.get("store_id"), "nested Workflow Store ID"
    )
    _, _, agent_end = _assert_store(
        stores.get(agent_store_id),
        expected_owner_span_id=agent_span_id,
        expected_owner_type="agent",
        expected_actions=None,
        apply_patch=apply_patch,
    )
    _, _, outer_end = _assert_store(
        stores.get(outer_store_id),
        expected_owner_span_id=outer_span_id,
        expected_owner_type="workflow",
        expected_actions=None,
        apply_patch=apply_patch,
    )
    _, _, nested_end = _assert_store(
        stores.get(nested_store_id),
        expected_owner_span_id=nested_span_id,
        expected_owner_type="workflow",
        expected_actions=["set_prepared_prompt", "set_artifact"],
        apply_patch=apply_patch,
    )
    studio_support.require(
        agent_end.get("final_output") == expectations.agent_output
        and outer_end.get("response") == expectations.agent_output
        and outer_end.get("agent_run_id") == expectations.agent_run_id
        and outer_end.get("directive") == "general_response"
        and nested_end.get("artifact") == expectations.artifact,
        "verified Store terminal states do not match the application result",
    )
    outer_actions = {
        transition.get("action")
        for transition in _list(
            _object(stores[outer_store_id], "outer Store annotation")["detail"].get(
                "transitions"
            ),
            "outer Store transitions",
        )
    }
    studio_support.require(
        outer_actions
        == {
            "set_recent_turns",
            "set_contact",
            "set_directive",
            "set_response",
            "set_persisted_turn",
        },
        "outer Workflow Store action set is incorrect",
    )
    studio_support.require(
        outer_annotation.get("runtime_id") == expectations.workflow_run_id
        and nested_annotation.get("runtime_id") == nested_runtime_id,
        "Workflow annotation runtime identity is incorrect",
    )
    return SemanticIdentities(
        trace_id=trace_id,
        outer_workflow_span_id=outer_span_id,
        agent_span_id=agent_span_id,
        general_response_span_id=general_span_id,
        tool_span_id=tool_span_id,
        nested_workflow_span_id=nested_span_id,
        nested_workflow_runtime_id=nested_runtime_id,
    )


def fetch_execution_resolution(
    client: studio_support.JsonClient,
    *,
    executable_type: str,
    runtime_id: str,
    timeout_seconds: float,
    interval_seconds: float,
    expected_trace_id: str | None = None,
    expected_span_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one semantic runtime identity to exact physical evidence."""

    query = urllib.parse.urlencode(
        {
            "service_namespace": SERVICE_NAMESPACE,
            "service_name": SERVICE_NAME,
            "executable_type": executable_type,
            "runtime_id": runtime_id,
        }
    )
    resolution = studio_support.bounded_poll(
        lambda: client.request(f"/api/v1/execution-resolution?{query}"),
        accept=lambda value: isinstance(value, dict),
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description=f"exact {executable_type} execution resolution",
    )
    resolved = _object(resolution, "execution resolution")
    _exact_keys(
        resolved,
        {
            "service_namespace",
            "service_name",
            "executable_type",
            "runtime_id",
            "trace_id",
            "span_id",
            "detail_path",
            "trace_path",
        },
        "execution resolution",
    )
    trace_id = _nonempty_text(resolved.get("trace_id"), "resolved trace ID")
    span_id = _nonempty_text(resolved.get("span_id"), "resolved span ID")
    expected_detail_path = (
        f"/agents/{trace_id}/{span_id}"
        if executable_type == "agent"
        else f"/workflows/{urllib.parse.quote(SERVICE_NAME, safe='')}/{trace_id}/{span_id}"
    )
    studio_support.require(
        resolved
        == {
            "service_namespace": SERVICE_NAMESPACE,
            "service_name": SERVICE_NAME,
            "executable_type": executable_type,
            "runtime_id": runtime_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "detail_path": expected_detail_path,
            "trace_path": (
                f"/traces/{urllib.parse.quote(SERVICE_NAME, safe='')}/{trace_id}/{span_id}"
            ),
        },
        "Studio resolved the semantic identity to the wrong evidence",
    )
    if expected_trace_id is not None:
        studio_support.require(trace_id == expected_trace_id, "resolved trace ID drifted")
    if expected_span_id is not None:
        studio_support.require(span_id == expected_span_id, "resolved span ID drifted")
    return resolved


def fetch_trace_evidence(
    client: studio_support.JsonClient,
    *,
    trace_id: str,
    agent_run_id: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    """Poll until the cohesive document contains the complete Agent trace."""

    def load() -> object:
        return client.request(f"/api/v1/trace-evidence/{trace_id}")

    def complete(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        spans = value.get("spans")
        executables = value.get("executables_by_span_id")
        return (
            isinstance(spans, list)
            and len(spans) == EXPECTED_SPAN_COUNT
            and isinstance(executables, dict)
            and any(
                isinstance(annotation, dict)
                and annotation.get("runtime_id") == agent_run_id
                for annotation in executables.values()
            )
        )

    return _object(
        studio_support.bounded_poll(
            load,
            accept=complete,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            description="the complete AI Chat TraceEvidence document",
        ),
        "TraceEvidence",
    )


def build_live_evidence(
    *, expectations: TurnExpectations, identities: SemanticIdentities
) -> dict[str, object]:
    """Build the credential-free handoff used by the Studio browser proof."""

    return {
        "schema_version": 2,
        "turn_id": expectations.turn_id,
        "service_namespace": SERVICE_NAMESPACE,
        "service_name": SERVICE_NAME,
        "service_version": expectations.service_version,
        "trace_id": identities.trace_id,
        "outer_workflow_name": OUTER_WORKFLOW_NAME,
        "outer_workflow_run_id": expectations.workflow_run_id,
        "outer_workflow_span_id": identities.outer_workflow_span_id,
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
    """Atomically publish evidence only after the complete proof succeeds."""

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


def run_browser_proof(
    *,
    frontend_url: str,
    backend_url: str,
    screenshot: Path,
    timeout_seconds: float,
    identity: studio_support.TestIdentity,
    evidence: Mapping[str, object],
) -> None:
    """Run the stable resolver and cohesive-evidence UI with fresh credentials."""

    with tempfile.TemporaryDirectory(
        prefix="junjo-ai-chat-browser-evidence-"
    ) as directory:
        evidence_path = Path(directory) / "evidence.json"
        write_live_evidence(evidence_path, evidence)
        environment = os.environ.copy()
        environment["JUNJO_STUDIO_E2E_EXISTING_EMAIL"] = identity.email
        environment["JUNJO_STUDIO_E2E_EXISTING_PASSWORD"] = identity.password
        command = [
            "node",
            str(REPOSITORY_ROOT / "apps/studio/frontend/e2e/live-ai-chat-agent.mjs"),
            "--frontend-url",
            frontend_url,
            "--backend-url",
            backend_url,
            "--evidence",
            str(evidence_path),
            "--screenshot",
            str(screenshot),
            "--timeout-milliseconds",
            str(max(1, round(timeout_seconds * 1000))),
        ]
        try:
            subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise studio_support.StudioE2EError(
                "Studio browser proof failed"
            ) from error


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
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )
        agent_resolution = fetch_execution_resolution(
            studio,
            executable_type="agent",
            runtime_id=expectations.agent_run_id,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )
        trace_id = _nonempty_text(agent_resolution.get("trace_id"), "Agent trace ID")
        trace_evidence = fetch_trace_evidence(
            studio,
            trace_id=trace_id,
            agent_run_id=expectations.agent_run_id,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )

        def apply_patch(document: object, patch: list[dict[str, object]]) -> object:
            return jsonpatch.JsonPatch(patch).apply(document, in_place=False)

        identities = assert_trace_evidence(
            trace_evidence,
            expectations=expectations,
            apply_patch=apply_patch,
        )
        studio_support.require(
            agent_resolution.get("span_id") == identities.agent_span_id,
            "Agent resolver and TraceEvidence identities diverged",
        )
        for executable_type, runtime_id, span_id in (
            (
                "workflow",
                expectations.workflow_run_id,
                identities.outer_workflow_span_id,
            ),
            ("agent", expectations.agent_run_id, identities.agent_span_id),
            (
                "workflow",
                identities.nested_workflow_runtime_id,
                identities.nested_workflow_span_id,
            ),
        ):
            fetch_execution_resolution(
                studio,
                executable_type=executable_type,
                runtime_id=runtime_id,
                expected_trace_id=identities.trace_id,
                expected_span_id=span_id,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.poll_interval_seconds,
            )
        evidence = build_live_evidence(
            expectations=expectations,
            identities=identities,
        )
        if args.frontend_url is not None:
            run_browser_proof(
                frontend_url=args.frontend_url,
                backend_url=args.backend_url,
                screenshot=args.browser_screenshot,
                timeout_seconds=args.timeout_seconds,
                identity=identity,
                evidence=evidence,
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
        "AI Chat Studio E2E passed: asynchronous Turn admission and fresh SQLite "
        "reload, fourteen-span hybrid execution, one cohesive TraceEvidence "
        "document, exact runtime resolution, and three verified Store replays.",
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
    parser.add_argument(
        "--frontend-url",
        help="Optional Studio frontend origin for the live resolver and visual proof.",
    )
    parser.add_argument(
        "--browser-screenshot",
        type=Path,
        help="Required screenshot output when --frontend-url is supplied.",
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
        args.poll_interval_seconds > 0,
        "--poll-interval-seconds must be positive",
    )
    studio_support.require(
        (args.frontend_url is None) == (args.browser_screenshot is None),
        "--frontend-url and --browser-screenshot must be supplied together",
    )
    run(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except studio_support.StudioE2EError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
