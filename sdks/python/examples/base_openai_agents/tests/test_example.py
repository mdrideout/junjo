from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mixed_runtime_trace_and_evaluation_declarations() -> None:
    probe = Path(__file__).with_name("validation_probe.py")
    completed = subprocess.run(
        [sys.executable, str(probe)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert len(result["outputs"]) == 2
    assert all("Brooklyn" in output for output in result["outputs"])
    assert {"invoke_workflow", "invoke_agent", "execute_tool", "chat"}.issubset(result["operations"])
    assert {"agent", "function", "generation", "guardrail", "task", "turn"}.issubset(result["source_types"])
    assert set(result["agent_names"]) == {
        "Local place coordinator",
        "Local place reviewer",
    }
    assert set(result["task_names"]) == {
        "Authentic local place recommendation",
        "Local place realism review",
    }
    assert set(result["fixture_model_names"]) == {
        "deterministic-coordinator-v1",
        "deterministic-local-place-v1",
        "deterministic-reviewer-v1",
    }
    assert {"workflow", "agent", "node"}.issubset(result["junjo_types"])
    assert result["translated_payloads_complete"] is True
    assert result["model_payloads_complete"] is True
    assert result["tool_payloads_complete"] is True
    assert result["source_trace_count"] == 2
    assert result["native_owners_beneath_openai_tools"] is True
    assert set(result["targets"]) == {
        "Local place coordinator",
        "Local place specialist",
        "Local place workflow",
    }


def test_http_request_is_the_parent_of_the_mixed_runtime_trace() -> None:
    probe = Path(__file__).with_name("http_validation_probe.py")
    completed = subprocess.run(
        [sys.executable, str(probe)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["status_code"] == 200
    assert "Brooklyn" in result["response"]["response"]
    assert result["server_span_name"] == "POST /recommendations"
    assert result["workflow_parent_is_server"] is True
    assert result["workflow_shares_server_trace"] is True
