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

    assert "Brooklyn" in result["output"]
    assert {"invoke_workflow", "invoke_agent", "execute_tool"}.issubset(result["operations"])
    assert {"workflow", "agent", "node"}.issubset(result["junjo_types"])
    assert set(result["targets"]) == {
        "Local place coordinator",
        "Local place specialist",
        "Local place workflow",
    }
