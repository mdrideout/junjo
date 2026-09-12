"""Public-reference regressions that make otherwise valid exports unusable."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import griffe
import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("junjo_docs_export", SDK_ROOT / "docs/export_api.py")
assert SPEC is not None and SPEC.loader is not None
export_api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = export_api
SPEC.loader.exec_module(export_api)


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    output = tmp_path_factory.mktemp("python-reference")
    export_api.generate_api(output, export_api.DEFAULT_SURFACE, "test", "test", "next")
    return output


def page(reference, symbol):
    return export_api.output_path_for_symbol(reference, symbol).read_text()


def test_rst_fields_and_all_following_examples_are_retained(reference):
    store = page(reference, "junjo.BaseStore")
    assert "| `initial_state` | `StateT` | The initial state of the store." in store
    workflow = page(reference, "junjo.Workflow")
    for example in ("Example without hooks", "Example with hooks", "Passing Parameters to Factories"):
        assert f"**{example}**" in workflow
    assert "result = await workflow.execute()" in workflow
    assert "hooks.on_workflow_completed(log_completed)" in workflow
    assert "graph_factory=lambda: create_graph_with_dependency(my_emulator)" in workflow
    assert "junjo.Workflow.execute" in workflow
    factory = page(reference, "junjo.GraphFactory")
    assert "[`Workflow.execute`](/docs/python/api/junjo/workflow/#junjo.Workflow.execute)" in factory
    assert "[`Subflow.execute`](/docs/python/api/junjo/subflow/#junjo.Subflow.execute)" in factory


def test_markup_conversion_does_not_modify_example_code():
    text = '.. code-block:: python\n\n    message = "``literal`` :class:`KeepMe`"\n'
    assert export_api.markdown_text(text, "junjo", {}) == (
        '```python\nmessage = "``literal`` :class:`KeepMe`"\n```'
    )


def test_every_export_has_valid_fences_and_no_unconverted_rst(reference):
    manifest = json.loads((reference / "api-manifest.json").read_text())
    assert manifest["griffe_diagnostics"] == []
    for path in reference.rglob("*.md"):
        text = path.read_text()
        assert not re.search(r"^``(?:python|$)", text, re.MULTILINE), path
        assert len(re.findall(r"^```", text, re.MULTILINE)) % 2 == 0, path
        prose = re.sub(r"^```[^\n]*\n[\s\S]*?^```[ \t]*$", "", text, flags=re.MULTILINE)
        assert not re.search(r"^\.\. (?:rubric|code-block)::|^:(?:param|type|rtype)\b", prose, re.MULTILINE), path


def test_schemas_enums_and_callable_protocols_are_readable(reference):
    assert "id: RecordId" in page(reference, "junjo.studio.DatasetRead")
    assert "status: AttemptStatus" in page(reference, "junjo.studio.AttemptRead")
    assert "detail_path:" in page(reference, "junjo.studio.ExecutionResolutionRead")
    assert "DRAFT = 'draft'" in page(reference, "junjo.studio.DatasetStatus")
    assert "JUDGE = 'judge'" in page(reference, "junjo.evaluation.EvaluationRole")
    assert "__call__(input: ToolInputT, context: AgentRunContext[DependenciesT]) -> ToolOutputT" in page(
        reference, "junjo.agent.tool.ToolService"
    )
    aliases = (reference / "docs/python/api/junjo/agent/json/index.md").read_text()
    assert "JsonScalar: TypeAlias = None | bool | int | float | str" in aliases
    assert 'id="junjo.agent.json.FrozenJsonValue"' in aliases


def test_every_contracted_target_has_a_real_anchor(reference):
    manifest = json.loads((reference / "api-manifest.json").read_text())
    for symbol in manifest["symbols"]:
        text = (reference / symbol["target_route"].strip("/") / "index.md").read_text()
        assert f'id="{symbol["target_anchor"]}"' in text, symbol["public_name"]


def test_documented_class_fields_include_owned_inherited_fields():
    surface = export_api.load_surface(export_api.DEFAULT_SURFACE)
    names = {entry["public_name"] for entry in surface["objects"]}
    package = griffe.load("junjo", search_paths=[SDK_ROOT / "src"], docstring_parser="auto")
    for entry in surface["objects"]:
        if entry["kind"] not in {"class", "exception"} or entry["public_name"] != entry["anchor"]:
            continue
        obj = export_api.resolve_object(package, entry["public_name"])
        members = dict(obj.inherited_members)
        members.update(obj.members)
        for name, member in members.items():
            if name.startswith("_") or name == "model_config":
                continue
            member = member.final_target if member.is_alias else member
            if member.kind == griffe.Kind.ATTRIBUTE:
                assert f"{entry['public_name']}.{name}" in names


def test_node_helper_points_to_studio_evaluations(reference):
    text = page(reference, "junjo.evaluate_node")
    assert "Junjo intentionally does not own datasets" not in text
    assert "EvaluationHarness" in text and "NodeTarget" in text
    assert "Studio stores the datasets, outcomes" in text


def test_evidence_and_comparison_fields_explain_their_meaning(reference):
    assert "operational errors are distinct from failed judgments" in page(reference, "junjo.studio.AttemptRead")
    assert "not an automatically accepted generated answer" in page(reference, "junjo.studio.CaseCreate")
    assert "fraction from 0 to 1" in page(reference, "junjo.studio.OutcomeSummary")
    assert "Candidate subject duration minus baseline duration" in page(
        reference, "junjo.studio.RunComparisonRow"
    )
    assert "observation count" in page(reference, "junjo.agent.result.AgentUsage")
    assert "Serialized JSON Patch" in page(reference, "junjo.hooks.StateChangedEvent")
