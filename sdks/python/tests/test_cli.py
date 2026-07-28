"""JSON and configuration contracts for the installed Junjo CLI."""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

from junjo.cli.main import EXIT_EVALUATION, EXIT_OK, EXIT_SUBJECT, EXIT_USAGE
from junjo.evaluation import (
    EvaluationHarness,
    ExactMatchEvaluator,
    ExecutionServiceIdentity,
    NodeTarget,
)
from junjo.studio import AttemptStatus, StudioHealth

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
            input_version=1,
            input_type=CliInput,
            factory=lambda _input, _context, _resources: None,
            projector=lambda _result, _input, _context, _resources: None,
        ),
    ),
    evaluators=(ExactMatchEvaluator(),),
    runtime_context=resources,
)


class FakeStudioClient:
    created_request = None

    def __init__(self, **_configuration: object) -> None:
        pass

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
    assert payload["data"]["targets"][0]["input_schema"]["additionalProperties"] is False


def test_help_uses_argparse_normally_without_an_internal_error(capsys) -> None:
    exit_code = cli.main(["eval", "--help"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "Build and execute Studio-backed evaluation datasets." in captured.out
    assert '"ok":false' not in captured.out
    assert captured.err == ""


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
    secret = "junjo_eval_private-control-token"

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
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", "junjo_eval_test.secret")

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


def test_run_exit_codes_distinguish_completion_regression_and_error() -> None:
    def detail(*statuses: AttemptStatus):
        return SimpleNamespace(
            cases=tuple(SimpleNamespace(attempt=SimpleNamespace(status=status)) for status in statuses)
        )

    assert cli._run_exit_code(detail(AttemptStatus.PASSED)) == EXIT_OK
    assert cli._run_exit_code(detail(AttemptStatus.FAILED)) == EXIT_EVALUATION
    assert cli._run_exit_code(detail(AttemptStatus.FAILED, AttemptStatus.ERROR)) == EXIT_SUBJECT
