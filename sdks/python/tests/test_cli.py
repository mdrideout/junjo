"""JSON and configuration contracts for the installed Junjo CLI."""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

from junjo.cli.main import EXIT_CONFLICT, EXIT_EVALUATION, EXIT_OK, EXIT_SUBJECT, EXIT_USAGE
from junjo.evaluation import (
    EvaluationHarness,
    ExactMatchEvaluator,
    ExecutionServiceIdentity,
    NodeTarget,
)
from junjo.studio import (
    AttemptStatus,
    ExecutableType,
    ExecutionIdentityAmbiguous,
    ExecutionResolutionConflict,
    SemanticExecutionReference,
    StudioHealth,
)

cli = importlib.import_module("junjo.cli.main")


class CliInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str


@asynccontextmanager
async def resources() -> AsyncIterator[object]:
    yield object()


HARNESS = EvaluationHarness(
    application_key="cli_test",
    service_identity=ExecutionServiceIdentity(
        service_namespace="junjo.tests",
        service_name="cli",
    ),
    targets=(
        NodeTarget(
            key="message",
            name="Message Node",
            input_version=1,
            input_type=CliInput,
            factory=lambda _input, _context, _resources: None,
            projector=lambda _result, _input, _context, _resources: None,
        ),
    ),
    evaluators=(ExactMatchEvaluator(),),
    runtime_context=resources,
)


class AttributeDict(dict):
    def __getattr__(self, name: str):
        return self[name]


class FakeStudioClient:
    created_request = None
    membership_evidence = None
    configuration: dict[str, object] | None = None
    evidence_calls: list[tuple[str, object]] = []

    def __init__(self, **configuration: object) -> None:
        type(self).configuration = configuration

    async def __aenter__(self) -> FakeStudioClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get_health(self) -> StudioHealth:
        return StudioHealth(
            status="ok",
            version="0.82.1",
            app_name="Junjo AI Studio",
        )

    async def create_dataset(self, request):
        type(self).created_request = request
        return {
            "id": "dataset-id",
            "application_key": request.application_key,
            "key": request.key,
        }

    async def get_evidence_membership(self, evidence, *, cursor=None, limit=50):
        type(self).membership_evidence = evidence
        return {"kind": evidence.kind, "cursor": cursor, "limit": limit}

    async def get_attempt(self, attempt_id):
        type(self).evidence_calls.append(("attempt", attempt_id))
        return SimpleNamespace(dataset=SimpleNamespace(application_key="cli_test"))

    async def get_attempt_evidence_manifest(self, attempt_id):
        type(self).evidence_calls.append(("manifest", attempt_id))
        return {"attempt_id": attempt_id, "level": "manifest"}

    async def get_attempt_evidence_spans(self, attempt_id, span_ids):
        type(self).evidence_calls.append(("spans", tuple(span_ids)))
        return {"attempt_id": attempt_id, "span_ids": list(span_ids)}

    async def get_attempt_evidence(self, attempt_id):
        type(self).evidence_calls.append(("full", attempt_id))
        return AttributeDict(
            attempt=AttributeDict(
                dataset=AttributeDict(application_key="cli_test"),
            ),
            level="full",
        )


def _payload(capsys) -> dict:
    output = capsys.readouterr()
    assert output.out.count("\n") == 1
    return json.loads(output.out)


def test_targets_list_is_provider_free_and_machine_readable(capsys) -> None:
    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "targets",
            "list",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload["schema_version"] == 1
    assert payload["ok"] is True
    assert payload["data"]["application_key"] == "cli_test"
    assert payload["data"]["targets"][0]["name"] == "Message Node"
    assert payload["data"]["targets"][0]["input_schema"]["additionalProperties"] is False


def test_evaluators_list_is_provider_free_and_machine_readable(capsys) -> None:
    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "evaluators",
            "list",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    evaluator = payload["data"]["evaluators"][0]
    assert evaluator["key"] == "junjo.exact"
    assert evaluator["version"] == 1
    assert evaluator["role"] == "verifier"
    assert evaluator["expectation_schema"]["additionalProperties"] is False


def test_help_uses_argparse_normally_without_an_internal_error(capsys) -> None:
    exit_code = cli.main(["eval", "--help"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "Build and execute Studio-backed evaluation datasets." in captured.out
    assert '"ok":false' not in captured.out
    assert captured.err == ""


def test_explain_markdown_is_local_and_describes_staged_evidence(capsys) -> None:
    exit_code = cli.main(["eval", "explain"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert captured.out.startswith("# Junjo Evaluation CLI\n")
    assert "`junjo eval attempt evidence manifest --attempt-id ATTEMPT_ID`" in captured.out
    assert "`junjo eval attempt evidence spans --attempt-id ATTEMPT_ID" in captured.out
    assert "JUNJO_AI_STUDIO_CLI_TOKEN" in captured.out
    assert "Executes an evaluation target" in captured.out
    assert captured.err == ""


def test_explain_json_is_generated_from_command_and_argument_metadata(capsys) -> None:
    exit_code = cli.main(["eval", "explain", "--format", "json"])

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    commands = {item["command"]: item for item in payload["data"]["commands"]}
    spans = commands["junjo eval attempt evidence spans"]
    assert spans["evidence_level"] == "selected_spans"
    assert spans["executes_evaluation_target"] is False
    assert spans["authentication"] == "JUNJO_AI_STUDIO_CLI_TOKEN"
    span_argument = next(item for item in spans["arguments"] if item["name"] == "span_id")
    assert span_argument["required"] is True
    assert span_argument["repeatable"] is True
    assert commands["junjo eval run execute"]["executes_evaluation_target"] is True
    assert payload["data"]["configuration"][0]["pyproject"] == ("[tool.junjo.evaluation].harness")


def test_skill_path_is_local_and_requires_no_harness_or_studio(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    skill_directory = tmp_path / "junjo-evaluation"
    skill_directory.mkdir()
    skill_file = skill_directory / "SKILL.md"
    skill_file.write_text("---\nname: junjo-evaluation\n---\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_skill_directory", lambda name: skill_directory)

    exit_code = cli.main(["eval", "skill", "path"])

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload == {
        "command": "eval.skill.path",
        "data": {
            "name": "junjo-evaluation",
            "path": str(skill_directory),
            "skill_file": str(skill_file),
        },
        "ok": True,
        "schema_version": 1,
    }


def test_openai_agents_skill_path_uses_the_same_installed_skill_contract(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    skill_directory = tmp_path / "junjo-openai-agents"
    skill_directory.mkdir()
    skill_file = skill_directory / "SKILL.md"
    skill_file.write_text("---\nname: junjo-openai-agents\n---\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_skill_directory", lambda name: skill_directory)

    exit_code = cli.main(["eval", "skill", "path", "--name", "junjo-openai-agents"])

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload["data"] == {
        "name": "junjo-openai-agents",
        "path": str(skill_directory),
        "skill_file": str(skill_file),
    }


def test_pyproject_selects_one_explicit_harness(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (f'[tool.junjo.evaluation]\nharness = "{__name__}:HARNESS"\n'),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["eval", "targets", "list"])

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload["command"] == "eval.targets.list"


def test_capabilities_reports_sdk_studio_and_control_boundaries(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "capabilities",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload["data"]["sdk"]["telemetry_contract_version"] == 2
    assert payload["data"]["studio"]["version"] == "0.82.1"
    assert payload["data"]["control_api"] == {
        "authentication": "evaluation_control_token",
        "telemetry_transport": "otlp",
        "version": 1,
    }
    assert payload["data"]["agent_guidance"] == {
        "skill_name": "junjo-evaluation",
        "skill_discovery_command": "junjo eval skill path",
        "interface_explainer_command": "junjo eval explain",
        "interface_explainer_json_command": "junjo eval explain --format json",
    }
    assert [level["name"] for level in payload["data"]["evidence_access"]] == [
        "attempt_summary",
        "manifest",
        "selected_spans",
        "full",
    ]


def test_backend_base_url_comes_from_the_explicit_environment_variable(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.configuration = None
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv(
        "JUNJO_AI_STUDIO_BACKEND_BASE_URL",
        "http://studio-api.test:26154",
    )

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "capabilities",
        ]
    )

    _payload(capsys)
    assert exit_code == EXIT_OK
    assert FakeStudioClient.configuration == {"base_url": "http://studio-api.test:26154"}


def test_backend_base_url_defaults_to_the_local_studio_api(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.configuration = None
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.delenv("JUNJO_AI_STUDIO_BACKEND_BASE_URL", raising=False)

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "capabilities",
        ]
    )

    _payload(capsys)
    assert exit_code == EXIT_OK
    assert FakeStudioClient.configuration == {"base_url": "http://localhost:26154"}


def test_backend_base_url_rejects_an_empty_environment_variable(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.configuration = None
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv("JUNJO_AI_STUDIO_BACKEND_BASE_URL", "")

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "capabilities",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_USAGE
    assert payload["error"]["message"] == ("JUNJO_AI_STUDIO_BACKEND_BASE_URL cannot be empty.")
    assert FakeStudioClient.configuration is None


def test_backend_base_url_flag_overrides_the_environment_variable(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.configuration = None
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv(
        "JUNJO_AI_STUDIO_BACKEND_BASE_URL",
        "http://environment.test:26154",
    )

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "--studio-backend-base-url",
            "http://explicit.test:26154",
            "capabilities",
        ]
    )

    _payload(capsys)
    assert exit_code == EXIT_OK
    assert FakeStudioClient.configuration == {"base_url": "http://explicit.test:26154"}


def test_control_commands_require_environment_token_without_echoing_it(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.delenv("JUNJO_AI_STUDIO_CLI_TOKEN", raising=False)

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "dataset",
            "list",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_USAGE
    assert payload["error"]["code"] == "usage_or_validation"
    assert "JUNJO_AI_STUDIO_CLI_TOKEN" in payload["error"]["message"]


def test_run_list_requires_an_application_scoped_dataset(capsys) -> None:
    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "run",
            "list",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_USAGE
    assert payload["error"]["code"] == "usage_or_validation"
    assert "--dataset-id" in payload["error"]["message"]


def test_unexpected_errors_never_echo_the_control_token(
    monkeypatch,
    capsys,
) -> None:
    secret = "jcli_private-control-token"

    class FailingStudioClient:
        def __init__(self, **_configuration: object) -> None:
            raise RuntimeError(secret)

    monkeypatch.setattr(cli, "StudioClient", FailingStudioClient)
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", secret)

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "dataset",
            "list",
        ]
    )

    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["error"]["message"] == "Unexpected RuntimeError."
    assert secret not in json.dumps(payload)
    assert secret not in captured.err


def test_dataset_create_uses_harness_application_and_scoped_client(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.created_request = None
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", "jcli_test-token")

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "dataset",
            "create",
            "--key",
            "places",
            "--name",
            "Local places",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_OK
    assert payload["data"]["application_key"] == "cli_test"
    assert FakeStudioClient.created_request.application_key == "cli_test"


def test_evidence_membership_accepts_native_and_external_evidence(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", "jcli_test-token")

    native_exit = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "evidence",
            "membership",
            "--kind",
            "junjo_execution",
            "--executable-type",
            "workflow",
            "--runtime-id",
            "workflow-run",
        ]
    )
    native_payload = _payload(capsys)

    assert native_exit == EXIT_OK
    assert native_payload["data"]["kind"] == "junjo_execution"
    assert FakeStudioClient.membership_evidence.service_name == "cli"

    external_exit = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "evidence",
            "membership",
            "--kind",
            "otel_span",
            "--trace-id",
            "1" * 32,
            "--span-id",
            "a" * 16,
        ]
    )
    external_payload = _payload(capsys)

    assert external_exit == EXIT_OK
    assert external_payload["data"]["kind"] == "otel_span"
    assert FakeStudioClient.membership_evidence.trace_id == "1" * 32


def test_attempt_evidence_commands_are_explicit_and_select_span_ids(
    monkeypatch,
    capsys,
) -> None:
    FakeStudioClient.evidence_calls = []
    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", "jcli_test-token")
    prefix = ["eval", "--harness", f"{__name__}:HARNESS", "attempt", "evidence"]

    manifest_exit = cli.main([*prefix, "manifest", "--attempt-id", "attempt-1"])
    manifest_payload = _payload(capsys)
    spans_exit = cli.main(
        [
            *prefix,
            "spans",
            "--attempt-id",
            "attempt-1",
            "--span-id",
            "a" * 16,
            "--span-id",
            "b" * 16,
        ]
    )
    spans_payload = _payload(capsys)
    full_exit = cli.main([*prefix, "full", "--attempt-id", "attempt-1"])
    full_payload = _payload(capsys)

    assert (manifest_exit, spans_exit, full_exit) == (EXIT_OK, EXIT_OK, EXIT_OK)
    assert manifest_payload["command"] == "eval.attempt.evidence.manifest"
    assert spans_payload["data"]["span_ids"] == ["a" * 16, "b" * 16]
    assert full_payload["command"] == "eval.attempt.evidence.full"
    assert FakeStudioClient.evidence_calls == [
        ("attempt", "attempt-1"),
        ("manifest", "attempt-1"),
        ("attempt", "attempt-1"),
        ("spans", ("a" * 16, "b" * 16)),
        ("full", "attempt-1"),
    ]


def test_attempt_manifest_reports_semantic_resolution_conflict(monkeypatch, capsys) -> None:
    async def raise_conflict(_client, _attempt_id):
        raise ExecutionIdentityAmbiguous(
            SemanticExecutionReference(
                service_namespace="junjo.tests",
                service_name="cli",
                executable_type=ExecutableType.WORKFLOW,
                runtime_id="workflow-run",
            ),
            ExecutionResolutionConflict(
                code="ambiguous_execution_identity",
                message="two matches",
                match_count=2,
            ),
        )

    monkeypatch.setattr(cli, "StudioClient", FakeStudioClient)
    monkeypatch.setattr(FakeStudioClient, "get_attempt_evidence_manifest", raise_conflict)
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", "jcli_test-token")

    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "attempt",
            "evidence",
            "manifest",
            "--attempt-id",
            "attempt-1",
        ]
    )
    payload = _payload(capsys)

    assert exit_code == EXIT_CONFLICT
    assert payload["error"]["code"] == "conflict"
    assert "2 executions" in payload["error"]["message"]


def test_old_ambiguous_attempt_evidence_command_is_removed(capsys) -> None:
    exit_code = cli.main(
        [
            "eval",
            "--harness",
            f"{__name__}:HARNESS",
            "attempt",
            "evidence",
            "--attempt-id",
            "attempt-1",
        ]
    )

    payload = _payload(capsys)
    assert exit_code == EXIT_USAGE
    assert payload["error"]["code"] == "usage_or_validation"
    assert "attempt_evidence_command" in payload["error"]["message"]


def test_run_exit_codes_distinguish_completion_regression_and_error() -> None:
    def detail(*statuses: AttemptStatus):
        return SimpleNamespace(
            cases=tuple(SimpleNamespace(attempt=SimpleNamespace(status=status)) for status in statuses)
        )

    assert cli._run_exit_code(detail(AttemptStatus.PASSED)) == EXIT_OK
    assert cli._run_exit_code(detail(AttemptStatus.FAILED)) == EXIT_EVALUATION
    assert cli._run_exit_code(detail(AttemptStatus.FAILED, AttemptStatus.ERROR)) == EXIT_SUBJECT
