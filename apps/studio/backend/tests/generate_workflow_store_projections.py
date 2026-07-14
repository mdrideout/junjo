"""Generate frontend projections from canonical Workflow Store evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.features.workflow_diagnostics.assembler import (
    assemble_workflow_store_diagnostic,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "contracts" / "telemetry" / "fixtures" / "workflow"
OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "apps"
    / "studio"
    / "frontend"
    / "src"
    / "features"
    / "workflow-executions"
    / "testing"
    / "workflow-store-projections.json"
)


def generate_projections() -> list[dict[str, Any]]:
    projections: list[dict[str, Any]] = []
    for path in sorted(FIXTURE_ROOT.glob("*.json")):
        fixture = json.loads(path.read_text())
        for owner in fixture["spans"]:
            if owner["attributes_json"].get("junjo.span_type") not in {
                "workflow",
                "subflow",
            }:
                continue
            detail = assemble_workflow_store_diagnostic(owner, fixture["spans"])
            projections.append(
                {
                    "case_name": f"{path.stem}:{owner['span_id']}",
                    "detail": detail.model_dump(mode="json"),
                }
            )
    return sorted(projections, key=lambda item: item["case_name"])


def render_projections() -> str:
    return json.dumps(
        generate_projections(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_projections())
    print(f"Wrote {len(generate_projections())} Workflow projections to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
