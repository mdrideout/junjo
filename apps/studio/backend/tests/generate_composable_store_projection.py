"""Publish backend evidence for the shared-Store frontend and SDK contract tests."""

from pathlib import Path

from tests.test_composable_store_evidence import projection

OUTPUT = Path(__file__).parent / "generated/composable_store_trace.json"


def render_projection() -> str:
    return projection()[1].model_dump_json(indent=2) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render_projection())
