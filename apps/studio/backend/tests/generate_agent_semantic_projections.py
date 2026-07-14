"""Generate frontend-facing projections from canonical Agent span fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.features.agent_diagnostics.assembler import assemble_agent_detail

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "contracts" / "telemetry" / "fixtures" / "agent"
OUTPUT_PATH = Path(__file__).resolve().parent / "generated" / "agent_semantic_projections.json"


def fixture_paths() -> list[Path]:
    """Return every valid producer and consumer fixture in deterministic order."""
    return sorted([*(FIXTURE_ROOT / "producer").glob("*.json"), *(FIXTURE_ROOT / "consumer").glob("*.json")])


def generate_projections() -> list[dict[str, Any]]:
    """Assemble every canonical Agent owner through the authoritative backend."""
    projections: list[dict[str, Any]] = []
    for fixture_path in fixture_paths():
        fixture = json.loads(fixture_path.read_text())
        owners = [
            span
            for span in fixture["spans"]
            if span["attributes_json"].get("junjo.span_type") == "agent"
        ]
        for index, owner in enumerate(owners, start=1):
            detail = assemble_agent_detail(owner, fixture["spans"])
            case_name = fixture["scenario"] if len(owners) == 1 else f"{fixture['scenario']}__agent_{index}"
            projections.append(
                {
                    "case_name": case_name,
                    "summary": detail.summary.model_dump(mode="json"),
                    "detail": detail.model_dump(mode="json"),
                }
            )
    return sorted(projections, key=lambda item: item["case_name"])


def render_projections() -> str:
    """Render canonical stable JSON suitable for checked-in equivalence tests."""
    return json.dumps(generate_projections(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_projections())
    print(f"Wrote {len(generate_projections())} Agent projections to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
