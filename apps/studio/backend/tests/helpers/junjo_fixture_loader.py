"""Load the shared current-Junjo transport fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = (
    Path(__file__).resolve().parents[3] / "test-fixtures" / "junjo-library-update"
)


def list_junjo_fixture_case_names() -> list[str]:
    """Return the available fixture case names."""
    return sorted(path.stem for path in FIXTURE_DIR.glob("*.json"))


def load_junjo_fixture_case(case_name: str) -> dict[str, Any]:
    """Load one shared fixture case by file stem."""
    fixture_path = FIXTURE_DIR / f"{case_name}.json"
    with fixture_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_all_junjo_fixture_cases() -> list[dict[str, Any]]:
    """Load every shared fixture case."""
    return [load_junjo_fixture_case(case_name) for case_name in list_junjo_fixture_case_names()]
