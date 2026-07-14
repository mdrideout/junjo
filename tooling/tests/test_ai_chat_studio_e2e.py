"""Offline fail-closed tests for the live AI Chat Studio validator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "tooling/scripts"


def load_validator() -> ModuleType:
    """Load the script while preserving its stdlib-only sibling import."""

    path = SCRIPTS_DIRECTORY / "validate_ai_chat_studio_e2e.py"
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))
    try:
        specification = importlib.util.spec_from_file_location(
            "validate_ai_chat_studio_e2e", path
        )
        if specification is None or specification.loader is None:
            raise RuntimeError(f"could not load {path}")
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        specification.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIRECTORY))


validator = load_validator()


def _messages() -> tuple[dict[str, object], dict[str, object]]:
    timestamp = "2026-07-14T04:00:00Z"
    image_id = "a" * 32
    return (
        {
            "id": "user-message",
            "turn_id": "turn-1",
            "role": "user",
            "content": validator.INPUT_TEXT,
            "image_url": None,
            "image_alt": None,
            "created_at": timestamp,
        },
        {
            "id": "assistant-message",
            "turn_id": "turn-1",
            "role": "assistant",
            "content": validator.ASSISTANT_TEXT,
            "image_url": f"/api/images/{image_id}.svg",
            "image_alt": validator.IMAGE_ALT,
            "created_at": timestamp,
        },
    )


def _turns() -> tuple[dict[str, object], dict[str, object]]:
    user, assistant = _messages()
    shared = {
        "object_type": "ai_chat.turn",
        "schema_version": 1,
        "id": "turn-1",
        "conversation_id": validator.CONVERSATION_ID,
        "sequence": 1,
        "context_policy": {
            "id": "recent-completed-turns",
            "version": 1,
            "recent_turn_limit": 8,
        },
        "user_message": user,
        "failure": None,
        "created_at": "2026-07-14T04:00:00Z",
    }
    admitted = {
        **shared,
        "revision": 0,
        "status": "admitted",
        "assistant_message": None,
        "execution_references": {
            "workflow_run_id": None,
            "agent_run_id": None,
        },
        "updated_at": "2026-07-14T04:00:00Z",
        "completed_at": None,
    }
    terminal = {
        **shared,
        "revision": 3,
        "status": "completed",
        "assistant_message": assistant,
        "execution_references": {
            "workflow_run_id": "outer-run",
            "agent_run_id": "agent-run",
        },
        "updated_at": "2026-07-14T04:00:02Z",
        "completed_at": "2026-07-14T04:00:02Z",
    }
    return admitted, terminal


def _expectations() -> object:
    user, assistant = _messages()
    return validator.TurnExpectations(
        service_version="0.1.0",
        workflow_run_id="outer-run",
        agent_run_id="agent-run",
        turn_id="turn-1",
        user_message=user,
        assistant_message=assistant,
        image_id="a" * 32,
    )


def _svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg"><g>'
        f"<text>{validator.INPUT_TEXT}</text>"
        "</g></svg>"
    )


def test_http_contract_proves_admission_polling_and_fresh_reload() -> None:
    admitted, terminal = _turns()

    result = validator.assert_http_turn(
        admitted_payload=admitted,
        terminal_payload=terminal,
        persistence_payload={
            "conversation_id": validator.CONVERSATION_ID,
            "turns": [terminal],
        },
        svg_status=200,
        svg_content_type="image/svg+xml; charset=utf-8",
        svg_text=_svg(),
        service_version="0.1.0",
    )

    assert result.turn_id == "turn-1"
    assert result.agent_run_id == "agent-run"
    assert result.workflow_run_id == "outer-run"
    assert result.artifact["url"] == f"/api/images/{'a' * 32}.svg"


def test_http_contract_rejects_client_side_terminal_identity() -> None:
    admitted, terminal = _turns()
    admitted["execution_references"] = {
        "workflow_run_id": "client-workflow",
        "agent_run_id": None,
    }

    with pytest.raises(validator.studio_support.StudioE2EError):
        validator.assert_http_turn(
            admitted_payload=admitted,
            terminal_payload=terminal,
            persistence_payload={
                "conversation_id": validator.CONVERSATION_ID,
                "turns": [terminal],
            },
            svg_status=200,
            svg_content_type="image/svg+xml",
            svg_text=_svg(),
            service_version="0.1.0",
        )


def test_live_evidence_handoff_is_exact_and_atomic(tmp_path: Path) -> None:
    expectations = _expectations()
    identities = validator.SemanticIdentities(
        trace_id="0" * 32,
        outer_workflow_span_id="a" * 16,
        agent_span_id="b" * 16,
        general_response_span_id="c" * 16,
        tool_span_id="d" * 16,
        nested_workflow_span_id="e" * 16,
        nested_workflow_runtime_id="nested-run",
    )

    evidence = validator.build_live_evidence(
        expectations=expectations,
        identities=identities,
    )
    output = tmp_path / "nested" / "evidence.json"
    validator.write_live_evidence(output, evidence)

    assert json.loads(output.read_text()) == evidence
    assert evidence["schema_version"] == 2
    assert evidence["outer_workflow_span_id"] == "a" * 16
    assert evidence["tool_operation_sequence"] == 2
    assert list(output.parent.glob(".evidence.json.*.tmp")) == []


class _ResolutionClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.paths: list[str] = []

    def request(self, path: str) -> dict[str, object]:
        self.paths.append(path)
        return self.response


def test_execution_resolution_requires_exact_physical_identity() -> None:
    trace_id = "0" * 32
    span_id = "a" * 16
    client = _ResolutionClient(
        {
            "service_namespace": validator.SERVICE_NAMESPACE,
            "service_name": validator.SERVICE_NAME,
            "executable_type": "agent",
            "runtime_id": "agent-run",
            "trace_id": trace_id,
            "span_id": span_id,
            "detail_path": f"/agents/{trace_id}/{span_id}",
            "trace_path": f"/traces/{validator.SERVICE_NAME}/{trace_id}/{span_id}",
        }
    )

    result = validator.fetch_execution_resolution(
        client,
        executable_type="agent",
        runtime_id="agent-run",
        expected_trace_id=trace_id,
        expected_span_id=span_id,
        timeout_seconds=1,
        interval_seconds=0.01,
    )

    assert result["span_id"] == span_id
    assert len(client.paths) == 1
    assert "runtime_id=agent-run" in client.paths[0]
