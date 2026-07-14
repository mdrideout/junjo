"""Subprocess static checks for the installed public Agent surface."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ty(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ty", "check", "--error-on-warning", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_public_agent_generics_typecheck_and_reject_crossed_boundaries() -> None:
    valid = _ty("tests/typing/agent_valid.py")
    assert valid.returncode == 0, valid.stdout + valid.stderr

    invalid = _ty("tests/typing/agent_invalid.py")
    diagnostics = invalid.stdout + invalid.stderr
    assert invalid.returncode != 0
    assert "invalid-assignment" in diagnostics
    assert "Output" in diagnostics
    assert "object" in diagnostics
