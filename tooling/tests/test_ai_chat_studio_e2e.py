"""Offline fail-closed tests for the live Horizon 2 Studio validator."""

from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

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


def full(value: object) -> dict[str, object]:
    return {
        "mode": "full",
        "policy": validator.FULL_POLICY,
        "value": copy.deepcopy(value),
        "reference": None,
        "reason": None,
    }


def apply_fixture_patch(document: object, patch: list[dict[str, object]]) -> object:
    result = copy.deepcopy(document)
    for operation in patch:
        if operation.get("op") != "replace" or operation.get("path") != "":
            raise AssertionError(f"unsupported fixture patch: {operation}")
        result = copy.deepcopy(operation["value"])
    return result


def integrity() -> dict[str, object]:
    return {
        "status": "complete",
        "diagnostics": [],
        "loss_counts": {
            "span_attributes": 0,
            "span_events": 0,
            "event_attributes": 0,
            "span_links": 0,
            "resource_attributes": 0,
        },
    }


def verified_store(
    start: dict[str, object],
    end: dict[str, object],
    *,
    actions: list[str],
) -> dict[str, object]:
    current = copy.deepcopy(start)
    revision = 0
    transitions: list[dict[str, object]] = []
    for sequence, action in enumerate(actions, start=1):
        patch = (
            [{"op": "replace", "path": "", "value": copy.deepcopy(end)}]
            if sequence == 1
            else []
        )
        after = apply_fixture_patch(current, patch)
        revision_after = revision + 1 if sequence == 1 else revision
        transitions.append(
            {
                "sequence": sequence,
                "revision_before": revision,
                "revision_after": revision_after,
                "span_id": f"{sequence:016x}",
                "event_id": f"event-{sequence}",
                "action": action,
                "patch": full(patch),
                "before": copy.deepcopy(current),
                "after": copy.deepcopy(after),
            }
        )
        current = after
        revision = revision_after
    return {
        "available": True,
        "store_id": f"store-{actions[0]}",
        "revision_start": 0,
        "revision_end": revision,
        "transition_count": len(transitions),
        "reconstructable_claimed": True,
        "reconstructable": True,
        "reconstruction_status": "verified",
        "reconstruction_reason": None,
        "start": full(start),
        "end": full(end),
        "transitions": transitions,
    }


def turn_expectations() -> object:
    image_id = "a" * 32
    timestamp = "2026-07-14T04:00:00Z"
    user = {
        "id": "user-message",
        "turn_id": "turn-1",
        "role": "user",
        "content": validator.INPUT_TEXT,
        "image_url": None,
        "image_alt": None,
        "created_at": timestamp,
    }
    assistant = {
        "id": "assistant-message",
        "turn_id": "turn-1",
        "role": "assistant",
        "content": validator.ASSISTANT_TEXT,
        "image_url": f"/api/images/{image_id}.svg",
        "image_alt": validator.IMAGE_ALT,
        "created_at": timestamp,
    }
    return validator.TurnExpectations(
        service_version="0.1.0",
        workflow_run_id="outer-run",
        agent_run_id="agent-run",
        turn_id="turn-1",
        user_message=user,
        assistant_message=assistant,
        image_id=image_id,
    )


def model_operation(
    *, sequence: int, ordinal: int, response_type: str
) -> dict[str, object]:
    return {
        "operation_type": "model_request",
        "sequence": sequence,
        "span_id": "f" * 16 if sequence == 1 else "2" * 16,
        "ordinal": ordinal,
        "outcome": "completed",
        "driver_key": "ai_chat_demo",
        "provider": "junjo",
        "model_name": "deterministic-demo-v1",
        "request": full({"messages": []}),
        "response_candidate": {"available": True, "payload": full({"v": 1})},
        "response_type": response_type,
        "response": full({"v": 1}),
        "requested_tool_calls": (
            [
                {
                    "call_id": "image-1",
                    "ordinal": 1,
                    "tool_name": "create_image",
                    "observed_tool_operation": True,
                    "admission": "admitted",
                    "reason": None,
                }
            ]
            if sequence == 1
            else []
        ),
    }


def agent_projection(
    expectations: object,
) -> tuple[dict[str, object], dict[str, object]]:
    summary = {
        "trace_id": "0" * 32,
        "agent_span_id": "e" * 16,
        "service": {
            "namespace": validator.SERVICE_NAMESPACE,
            "name": validator.SERVICE_NAME,
            "version": "0.1.0",
        },
        "agent_key": validator.AGENT_KEY,
        "agent_name": validator.AGENT_NAME,
        "runtime_id": expectations.agent_run_id,
        "outcome": "completed",
        "termination_reason": "final_output",
        "limits": {"model_requests": 4, "tool_calls": 4},
        "counts": {
            "operations": 3,
            "model_requests": 2,
            "tool_calls": {"requested": 1, "admitted": 1, "started": 1, "completed": 1},
        },
        "usage": {"model_responses": 2, "fields": {}},
    }
    tool = {
        "operation_type": "tool",
        "sequence": 2,
        "span_id": "1" * 16,
        "call_id": "image-1",
        "ordinal": 1,
        "tool_name": "create_image",
        "outcome": "completed",
        "requested_arguments": full({"prompt": validator.INPUT_TEXT}),
        "arguments": full({"prompt": validator.INPUT_TEXT}),
        "result_candidate": {
            "available": True,
            "payload": full({"artifact": expectations.artifact}),
        },
        "result": full({"artifact": expectations.artifact}),
    }
    start = validator._agent_state(expectations, final=False)
    end = validator._agent_state(expectations, final=True)
    detail = {
        "summary": copy.deepcopy(summary),
        "integrity": integrity(),
        "error": None,
        "cancellation": None,
        "definition": full({"key": validator.AGENT_KEY}),
        "input": full(expectations.agent_input),
        "output": full(expectations.agent_output),
        "operations": [
            model_operation(sequence=1, ordinal=1, response_type="tool_calls"),
            tool,
            model_operation(sequence=3, ordinal=2, response_type="final_output"),
        ],
        "state": verified_store(
            start, end, actions=[f"agent-action-{index}" for index in range(1, 9)]
        ),
        "parent_executable": {
            "executable_type": "node",
            "name": "ExecuteAgentNode",
            "trace_id": "0" * 32,
            "span_id": "c" * 16,
            "physical_parent_span_id": "c" * 16,
        },
        "nested_executables": [
            {
                "executable_type": "workflow",
                "name": validator.IMAGE_WORKFLOW_NAME,
                "parent_operation_sequence": 2,
                "parent_operation_span_id": "1" * 16,
                "trace_id": "0" * 32,
                "span_id": "3" * 16,
            }
        ],
    }
    return summary, detail


def raw_span(
    span_id: str,
    *,
    name: str,
    parent_span_id: str | None,
    attributes: dict[str, object],
) -> dict[str, object]:
    return {
        "trace_id": "0" * 32,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": validator.SERVICE_NAME,
        "name": name,
        "attributes_json": attributes,
        "events_json": [],
        "resource_attributes_json": {
            "service.namespace": validator.SERVICE_NAMESPACE,
            "service.name": validator.SERVICE_NAME,
            "service.version": "0.1.0",
        },
        "dropped_attributes_count": 0,
        "dropped_events_count": 0,
        "dropped_links_count": 0,
        "resource_dropped_attributes_count": 0,
    }


def raw_hierarchy() -> list[dict[str, object]]:
    def executable(
        kind: str,
        definition: str,
        runtime: str,
        structural: str,
    ) -> dict[str, object]:
        return {
            "junjo.span_type": kind,
            "junjo.executable_definition_id": definition,
            "junjo.executable_runtime_id": runtime,
            "junjo.executable_structural_id": structural,
        }

    def operation(kind: str, sequence: int) -> dict[str, object]:
        return {
            "junjo.agent.operation_type": kind,
            "junjo.agent.operation.sequence": sequence,
        }

    outer_id = "a" * 16
    execute_id = "c" * 16
    agent_id = "e" * 16
    tool_id = "1" * 16
    nested_id = "3" * 16
    execute_attributes = executable(
        "node", "execute-def", "execute-run", "execute-struct"
    )
    agent_attributes = {
        **executable("agent", "agent-def", "agent-run", "agent-struct"),
        "junjo.parent_executable_type": "node",
        "junjo.parent_executable_definition_id": "execute-def",
        "junjo.parent_executable_runtime_id": "execute-run",
        "junjo.parent_executable_structural_id": "execute-struct",
    }
    nested_attributes = {
        **executable("workflow", "nested-def", "nested-run", "nested-struct"),
        "junjo.parent_executable_type": "agent",
        "junjo.parent_executable_definition_id": "agent-def",
        "junjo.parent_executable_runtime_id": "agent-run",
        "junjo.parent_executable_structural_id": "agent-struct",
    }
    return [
        raw_span(
            outer_id,
            name=validator.OUTER_WORKFLOW_NAME,
            parent_span_id=None,
            attributes=executable("workflow", "outer-def", "outer-run", "outer-struct"),
        ),
        raw_span(
            "b" * 16,
            name="PersistInputNode",
            parent_span_id=outer_id,
            attributes=executable("node", "b-def", "b-run", "b-struct"),
        ),
        raw_span(
            execute_id,
            name="ExecuteAgentNode",
            parent_span_id=outer_id,
            attributes=execute_attributes,
        ),
        raw_span(
            "d" * 16,
            name="PersistResultNode",
            parent_span_id=outer_id,
            attributes=executable("node", "d-def", "d-run", "d-struct"),
        ),
        raw_span(
            agent_id,
            name=validator.AGENT_NAME,
            parent_span_id=execute_id,
            attributes=agent_attributes,
        ),
        raw_span(
            "f" * 16,
            name="agent.model_request",
            parent_span_id=agent_id,
            attributes=operation("model_request", 1),
        ),
        raw_span(
            tool_id,
            name="agent.tool",
            parent_span_id=agent_id,
            attributes=operation("tool", 2),
        ),
        raw_span(
            "2" * 16,
            name="agent.model_request",
            parent_span_id=agent_id,
            attributes=operation("model_request", 3),
        ),
        raw_span(
            nested_id,
            name=validator.IMAGE_WORKFLOW_NAME,
            parent_span_id=tool_id,
            attributes=nested_attributes,
        ),
        raw_span(
            "4" * 16,
            name="PrepareImagePromptNode",
            parent_span_id=nested_id,
            attributes=executable("node", "p-def", "p-run", "p-struct"),
        ),
        raw_span(
            "5" * 16,
            name="RenderImageNode",
            parent_span_id=nested_id,
            attributes=executable("node", "r-def", "r-run", "r-struct"),
        ),
    ]


class AIChatStudioE2EToolingTests(unittest.TestCase):
    """Exercise the proof's HTTP, semantic, replay, and hierarchy boundaries."""

    def test_exact_http_response_and_persistence_contract(self) -> None:
        expectations = turn_expectations()
        turn = {
            "conversation_id": validator.CONVERSATION_ID,
            "workflow_run_id": expectations.workflow_run_id,
            "agent_run_id": expectations.agent_run_id,
            "user_message": expectations.user_message,
            "assistant_message": expectations.assistant_message,
        }
        result = validator.assert_http_turn(
            turn_payload=turn,
            persistence_payload={
                "conversation_id": validator.CONVERSATION_ID,
                "messages": [expectations.user_message, expectations.assistant_message],
            },
            svg_status=200,
            svg_content_type="image/svg+xml; charset=utf-8",
            svg_text=(
                '<svg xmlns="http://www.w3.org/2000/svg"><g>'
                f"<text>{validator.INPUT_TEXT}</text>"
                "</g></svg>"
            ),
            service_version="0.1.0",
        )
        self.assertEqual(result, expectations)

        bad_persistence = {
            "conversation_id": validator.CONVERSATION_ID,
            "messages": [expectations.assistant_message, expectations.user_message],
        }
        with self.assertRaisesRegex(
            validator.studio_support.StudioE2EError, "persisted messages"
        ):
            validator.assert_http_turn(
                turn_payload=turn,
                persistence_payload=bad_persistence,
                svg_status=200,
                svg_content_type="image/svg+xml",
                svg_text=(
                    '<svg xmlns="http://www.w3.org/2000/svg"><g>'
                    f"<text>{validator.INPUT_TEXT}</text>"
                    "</g></svg>"
                ),
                service_version="0.1.0",
            )

    def test_live_evidence_handoff_is_exact_and_atomic(self) -> None:
        expectations = turn_expectations()
        identities = validator.SemanticIdentities(
            trace_id="0" * 32,
            agent_span_id="e" * 16,
            tool_span_id="1" * 16,
            nested_workflow_span_id="3" * 16,
            execute_agent_span_id="c" * 16,
        )
        evidence = validator.build_live_evidence(
            expectations=expectations,
            identities=identities,
            outer_span_id="a" * 16,
        )
        self.assertEqual(
            set(evidence),
            {
                "schema_version",
                "service_namespace",
                "service_name",
                "service_version",
                "trace_id",
                "outer_workflow_name",
                "outer_workflow_run_id",
                "outer_workflow_span_id",
                "agent_name",
                "agent_run_id",
                "agent_span_id",
                "tool_name",
                "tool_operation_sequence",
                "tool_span_id",
                "nested_workflow_name",
                "nested_workflow_span_id",
            },
        )
        self.assertEqual(evidence["agent_run_id"], "agent-run")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "evidence.json"
            validator.write_live_evidence(output, evidence)
            self.assertEqual(
                __import__("json").loads(output.read_text(encoding="utf-8")),
                evidence,
            )
            self.assertEqual(list(output.parent.glob(".*.tmp")), [])

    def test_agent_semantics_and_store_replay_fail_closed(self) -> None:
        expectations = turn_expectations()
        summary, detail = agent_projection(expectations)
        identities, store_id = validator.assert_agent_projection(
            summary_value=summary,
            detail_value=detail,
            expectations=expectations,
            apply_patch=apply_fixture_patch,
        )
        self.assertEqual(identities.tool_span_id, "1" * 16)
        self.assertTrue(store_id.startswith("store-"))

        detail["operations"][2]["sequence"] = 4
        with self.assertRaisesRegex(
            validator.studio_support.StudioE2EError, "sequence is not contiguous"
        ):
            validator.assert_agent_projection(
                summary_value=summary,
                detail_value=detail,
                expectations=expectations,
                apply_patch=apply_fixture_patch,
            )

    def test_workflow_projection_replays_and_checks_exact_state(self) -> None:
        start = {"value": "start"}
        end = {"value": "end"}
        projection = {
            "trace_id": "0" * 32,
            "workflow_span_id": "a" * 16,
            "executable_type": "workflow",
            "name": "Fixture Workflow",
            "integrity": integrity(),
            "state": verified_store(start, end, actions=["first", "second"]),
        }
        store_id = validator.assert_workflow_projection(
            projection,
            trace_id="0" * 32,
            span_id="a" * 16,
            name="Fixture Workflow",
            expected_states=(start, end),
            expected_actions=["first", "second"],
            apply_patch=apply_fixture_patch,
        )
        self.assertEqual(store_id, "store-first")

        projection["state"]["transitions"][1]["before"] = {"value": "tampered"}
        with self.assertRaisesRegex(
            validator.studio_support.StudioE2EError, "before projection is incorrect"
        ):
            validator.assert_workflow_projection(
                projection,
                trace_id="0" * 32,
                span_id="a" * 16,
                name="Fixture Workflow",
                expected_states=(start, end),
                expected_actions=["first", "second"],
                apply_patch=apply_fixture_patch,
            )

    def test_raw_hierarchy_requires_exact_physical_and_semantic_parentage(self) -> None:
        expectations = turn_expectations()
        identities = validator.SemanticIdentities(
            trace_id="0" * 32,
            agent_span_id="e" * 16,
            tool_span_id="1" * 16,
            nested_workflow_span_id="3" * 16,
            execute_agent_span_id="c" * 16,
        )
        outer_id, nested_runtime_id = validator.assert_raw_hierarchy(
            raw_hierarchy(),
            identities=identities,
            expectations=expectations,
        )
        self.assertEqual(outer_id, "a" * 16)
        self.assertEqual(nested_runtime_id, "nested-run")

        tampered = raw_hierarchy()
        nested = next(span for span in tampered if span["span_id"] == "3" * 16)
        nested["attributes_json"]["junjo.parent_executable_runtime_id"] = "wrong-agent"
        with self.assertRaisesRegex(
            validator.studio_support.StudioE2EError, "semantic Agent parent runtime_id"
        ):
            validator.assert_raw_hierarchy(
                tampered,
                identities=identities,
                expectations=expectations,
            )


if __name__ == "__main__":
    unittest.main()
