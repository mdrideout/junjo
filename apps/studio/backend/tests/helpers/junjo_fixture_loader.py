"""Load the shared current-Junjo transport fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACT_DIR = Path(__file__).resolve().parents[5] / "contracts" / "telemetry"
FIXTURE_DIR = CONTRACT_DIR / "fixtures" / "workflow"
AGENT_FIXTURE_DIR = CONTRACT_DIR / "fixtures" / "agent"
ACTIVE_CONTRACT_VERSION = int((CONTRACT_DIR / "VERSION").read_text(encoding="utf-8").strip())


def list_junjo_fixture_case_names() -> list[str]:
    """Return the available fixture case names."""
    return sorted(path.stem for path in FIXTURE_DIR.glob("*.json"))


def load_junjo_fixture_case(case_name: str) -> dict[str, Any]:
    """Load one shared fixture case by file stem."""
    fixture_path = FIXTURE_DIR / f"{case_name}.json"
    with fixture_path.open(encoding="utf-8") as handle:
        fixture = json.load(handle)
    if fixture.get("contract_version") != ACTIVE_CONTRACT_VERSION:
        raise ValueError(
            f"Fixture {case_name!r} does not target telemetry contract "
            f"{ACTIVE_CONTRACT_VERSION}."
        )
    return fixture


def load_all_junjo_fixture_cases() -> list[dict[str, Any]]:
    """Load every shared fixture case."""
    return [load_junjo_fixture_case(case_name) for case_name in list_junjo_fixture_case_names()]


def list_valid_transport_fixture_ids() -> list[str]:
    """Return Workflow plus valid Agent producer/consumer fixture identifiers."""
    fixture_ids = [f"workflow/{path.stem}" for path in FIXTURE_DIR.glob("*.json")]
    for fixture_kind in ("producer", "consumer"):
        fixture_ids.extend(
            f"agent/{fixture_kind}/{path.stem}"
            for path in (AGENT_FIXTURE_DIR / fixture_kind).glob("*.json")
        )
    return sorted(fixture_ids)


def load_valid_transport_fixture(fixture_id: str) -> dict[str, Any]:
    """Load one namespaced valid fixture used across the real transport path."""
    parts = fixture_id.split("/")
    if len(parts) == 2 and parts[0] == "workflow":
        path = FIXTURE_DIR / f"{parts[1]}.json"
    elif len(parts) == 3 and parts[0] == "agent" and parts[1] in {"producer", "consumer"}:
        path = AGENT_FIXTURE_DIR / parts[1] / f"{parts[2]}.json"
    else:
        raise ValueError(f"Unknown transport fixture ID {fixture_id!r}.")
    fixture = json.loads(path.read_text())
    if fixture.get("contract_version") != ACTIVE_CONTRACT_VERSION:
        raise ValueError(
            f"Fixture {fixture_id!r} does not target telemetry contract {ACTIVE_CONTRACT_VERSION}."
        )
    return fixture
