"""JSON-first command line interface for Junjo evaluation workflows."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, NoReturn

from pydantic import BaseModel, JsonValue, ValidationError

from ..evaluation import (
    CaseGenerationError,
    DirtySourceTreeError,
    EvaluationExecutor,
    EvaluationHarness,
    EvaluationRunError,
    EvaluatorContractError,
    EvaluatorExecutionError,
    EvaluatorNotRegisteredError,
    GenerateCaseRequest,
    HarnessConfigurationError,
    TargetContractError,
    TargetExecutionError,
    TargetNotRegisteredError,
)
from ..evaluation.context import EVALUATION_CONTEXT_VERSION
from ..studio import (
    AttemptExecutionUnavailable,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    DatasetCreate,
    ExecutableType,
    ExecutionEvidencePending,
    ExecutionIdentityAmbiguous,
    RunComparisonError,
    SemanticExecutionReference,
    StudioAuthenticationError,
    StudioAuthorizationError,
    StudioClient,
    StudioConflictError,
    StudioContractError,
    StudioRequestError,
    StudioTransientError,
    StudioValidationError,
    TargetKind,
)
from ..telemetry.otel_schema import JUNJO_TELEMETRY_CONTRACT_VERSION

JSON_ENVELOPE_VERSION = 1
DEFAULT_STUDIO_URL = "http://localhost:26154"

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_AUTHENTICATION = 3
EXIT_CONFLICT = 4
EXIT_SUBJECT = 5
EXIT_EVALUATION = 6
EXIT_PENDING_EVIDENCE = 7
EXIT_TRANSIENT = 8
EXIT_CONTRACT = 9


class CliUsageError(ValueError):
    """Command syntax or local configuration is invalid."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Raise a typed error instead of printing an unstructured usage failure."""

    def error(self, message: str) -> NoReturn:
        raise CliUsageError(message)


@dataclass(frozen=True, slots=True)
class CommandResult:
    data: object
    exit_code: int = EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the installed ``junjo`` command and return its exit status."""

    command = "unknown"
    try:
        arguments = _parser().parse_args(argv)
        command = arguments.command_path
        result = asyncio.run(_dispatch(arguments))
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else EXIT_INTERNAL
    except KeyboardInterrupt:
        return _emit_error(
            command=command,
            code="interrupted",
            message="The command was interrupted.",
            exit_code=130,
        )
    except BaseException as error:
        return _handle_error(command=command, error=error)

    _emit_success(command=command, data=result.data)
    return result.exit_code


async def _dispatch(arguments: argparse.Namespace) -> CommandResult:
    command = arguments.command_path
    if command == "eval.capabilities":
        harness = _load_optional_harness(arguments.harness)
        async with StudioClient(base_url=_studio_url(arguments.studio_url)) as client:
            health = await client.get_health()
        data: dict[str, object] = {
            "sdk": {
                "distribution": "junjo",
                "version": distribution_version("junjo"),
                "evaluation_context_version": EVALUATION_CONTEXT_VERSION,
                "telemetry_contract_version": JUNJO_TELEMETRY_CONTRACT_VERSION,
            },
            "studio": health,
            "control_api": {
                "version": 1,
                "authentication": "evaluation_control_token",
                "telemetry_transport": "otlp",
            },
        }
        if harness is not None:
            data["application"] = _harness_summary(harness, include_targets=False)
        return CommandResult(data)

    harness = _load_harness(arguments.harness)
    if command == "eval.targets.list":
        return CommandResult(_harness_summary(harness, include_targets=True))

    token = _studio_token()
    async with StudioClient(
        base_url=_studio_url(arguments.studio_url),
        token=token,
    ) as client:
        return await _dispatch_studio(
            arguments,
            client=client,
            harness=harness,
        )


async def _dispatch_studio(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    command = arguments.command_path
    if command.startswith("eval.dataset."):
        return await _dispatch_dataset(arguments, client=client, harness=harness)
    if command == "eval.case.generate":
        return await _generate_case(arguments, client=client, harness=harness)
    if command.startswith("eval.run."):
        return await _dispatch_run(arguments, client=client, harness=harness)
    if command.startswith("eval.attempt."):
        return await _dispatch_attempt(arguments, client=client, harness=harness)
    if command == "eval.execution.membership":
        return await _execution_membership(
            arguments,
            client=client,
            harness=harness,
        )
    raise AssertionError(f"Unhandled command {command}.")


async def _dispatch_dataset(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    command = arguments.command_path
    if command == "eval.dataset.create":
        return CommandResult(
            await client.create_dataset(
                DatasetCreate(
                    application_key=harness.application_key,
                    key=arguments.key,
                    name=arguments.name,
                    description=arguments.description,
                )
            )
        )
    if command == "eval.dataset.list":
        return CommandResult(
            await client.list_datasets(
                application_key=harness.application_key,
                cursor=arguments.cursor,
                limit=arguments.limit,
            )
        )
    if command == "eval.dataset.get":
        detail = await client.get_dataset(arguments.dataset_id)
        _require_application(harness, detail.dataset.application_key)
        return CommandResult(detail)
    if command == "eval.dataset.add":
        detail = await client.get_dataset(arguments.dataset_id)
        _require_application(harness, detail.dataset.application_key)
        input_json, expectation_json = _case_values(arguments)
        target_kind = TargetKind(arguments.target_kind)
        harness.validate_case_contract(
            target_kind=target_kind,
            target_key=arguments.target_key,
            input_version=arguments.input_version,
            input_json=input_json,
            evaluator_key=arguments.evaluator_key,
            evaluator_version=arguments.evaluator_version,
            expectation_json=expectation_json,
        )
        return CommandResult(
            await client.add_case(
                arguments.dataset_id,
                CaseCreate(
                    case_key=arguments.case_key,
                    origin=CaseOrigin.AUTHORED,
                    target_kind=target_kind,
                    target_key=arguments.target_key,
                    input_version=arguments.input_version,
                    input_json=input_json,
                    expectation_json=expectation_json,
                    evaluator_key=arguments.evaluator_key,
                    evaluator_version=arguments.evaluator_version,
                ),
            )
        )
    if command == "eval.dataset.lock":
        detail = await client.get_dataset(arguments.dataset_id)
        _require_application(harness, detail.dataset.application_key)
        for case in detail.cases:
            harness.prepare_case(case)
        return CommandResult(await client.lock_dataset(arguments.dataset_id))
    raise AssertionError(f"Unhandled dataset command {command}.")


async def _generate_case(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    input_json, expectation_json = _case_values(arguments)
    async with EvaluationExecutor(client=client, harness=harness) as executor:
        return CommandResult(
            await executor.generate_case(
                GenerateCaseRequest(
                    dataset_id=arguments.dataset_id,
                    case_key=arguments.case_key,
                    target_kind=TargetKind(arguments.target_kind),
                    target_key=arguments.target_key,
                    input_version=arguments.input_version,
                    input_json=input_json,
                    expectation_json=expectation_json,
                    evaluator_key=arguments.evaluator_key,
                    evaluator_version=arguments.evaluator_version,
                )
            )
        )


async def _dispatch_run(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    command = arguments.command_path
    if command in {"eval.run.execute", "eval.run.resume"}:
        async with EvaluationExecutor(client=client, harness=harness) as executor:
            if command == "eval.run.execute":
                detail = await executor.run(
                    dataset_id=arguments.dataset_id,
                    request_key=arguments.request_key,
                    candidate_label=arguments.candidate_label,
                )
            else:
                detail = await executor.resume(run_id=arguments.run_id)
        return CommandResult(detail, _run_exit_code(detail))
    if command == "eval.run.list":
        page = await client.list_runs(
            dataset_id=arguments.dataset_id,
            cursor=arguments.cursor,
            limit=arguments.limit,
        )
        foreign = [
            item.dataset.application_key
            for item in page.items
            if item.dataset.application_key != harness.application_key
        ]
        if foreign:
            raise CliUsageError("Studio returned runs for a different application.")
        return CommandResult(page)
    if command == "eval.run.get":
        detail = await client.get_run(arguments.run_id)
        _require_application(harness, detail.dataset.application_key)
        return CommandResult(detail)
    if command == "eval.run.compare":
        comparison = await client.compare_runs(
            arguments.baseline_run_id,
            arguments.candidate_run_id,
        )
        _require_application(harness, comparison.dataset.application_key)
        return CommandResult(comparison)
    raise AssertionError(f"Unhandled run command {command}.")


async def _dispatch_attempt(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    command = arguments.command_path
    if command == "eval.attempt.get":
        detail = await client.get_attempt(arguments.attempt_id)
        _require_application(harness, detail.dataset.application_key)
        return CommandResult(detail)
    if command == "eval.attempt.evidence":
        evidence = await client.get_attempt_evidence(arguments.attempt_id)
        _require_application(harness, evidence.attempt.dataset.application_key)
        return CommandResult(evidence)
    raise AssertionError(f"Unhandled attempt command {command}.")


async def _execution_membership(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    reference = SemanticExecutionReference(
        service_namespace=(
            harness.service_identity.service_namespace
            if arguments.service_namespace is None
            else arguments.service_namespace
        ),
        service_name=(
            harness.service_identity.service_name if arguments.service_name is None else arguments.service_name
        ),
        executable_type=ExecutableType(arguments.executable_type),
        runtime_id=arguments.runtime_id,
    )
    return CommandResult(
        await client.get_execution_membership(
            reference,
            cursor=arguments.cursor,
            limit=arguments.limit,
        )
    )


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        prog="junjo",
        description="Junjo application development commands.",
    )
    products = parser.add_subparsers(dest="product", required=True)
    evaluation = products.add_parser(
        "eval",
        help="Build and execute Studio-backed evaluation datasets.",
        description="Build and execute Studio-backed evaluation datasets.",
    )
    evaluation.add_argument(
        "--harness",
        help=(
            "Explicit module:object EvaluationHarness. Defaults to [tool.junjo.evaluation].harness in pyproject.toml."
        ),
    )
    evaluation.add_argument(
        "--studio-url",
        help=(f"Studio origin. Defaults to JUNJO_STUDIO_URL or {DEFAULT_STUDIO_URL}."),
    )
    commands = evaluation.add_subparsers(dest="eval_command", required=True)

    capabilities = commands.add_parser("capabilities")
    _select(capabilities, "eval.capabilities")

    targets = commands.add_parser("targets")
    target_commands = targets.add_subparsers(dest="targets_command", required=True)
    target_list = target_commands.add_parser("list")
    _select(target_list, "eval.targets.list")

    dataset = commands.add_parser("dataset")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_create = dataset_commands.add_parser("create")
    dataset_create.add_argument("--key", required=True)
    dataset_create.add_argument("--name", required=True)
    dataset_create.add_argument("--description")
    _select(dataset_create, "eval.dataset.create")

    dataset_list = dataset_commands.add_parser("list")
    _add_pagination(dataset_list)
    _select(dataset_list, "eval.dataset.list")

    dataset_get = dataset_commands.add_parser("get")
    dataset_get.add_argument("--dataset-id", required=True)
    _select(dataset_get, "eval.dataset.get")

    dataset_add = dataset_commands.add_parser("add")
    _add_case_arguments(dataset_add)
    _select(dataset_add, "eval.dataset.add")

    dataset_lock = dataset_commands.add_parser("lock")
    dataset_lock.add_argument("--dataset-id", required=True)
    _select(dataset_lock, "eval.dataset.lock")

    case = commands.add_parser("case")
    case_commands = case.add_subparsers(dest="case_command", required=True)
    case_generate = case_commands.add_parser("generate")
    _add_case_arguments(case_generate)
    _select(case_generate, "eval.case.generate")

    run = commands.add_parser("run")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    run_execute = run_commands.add_parser("execute")
    run_execute.add_argument("--dataset-id", required=True)
    run_execute.add_argument("--request-key", required=True)
    run_execute.add_argument("--candidate-label", required=True)
    _select(run_execute, "eval.run.execute")

    run_resume = run_commands.add_parser("resume")
    run_resume.add_argument("--run-id", required=True)
    _select(run_resume, "eval.run.resume")

    run_list = run_commands.add_parser("list")
    run_list.add_argument("--dataset-id", required=True)
    _add_pagination(run_list)
    _select(run_list, "eval.run.list")

    run_get = run_commands.add_parser("get")
    run_get.add_argument("--run-id", required=True)
    _select(run_get, "eval.run.get")

    run_compare = run_commands.add_parser("compare")
    run_compare.add_argument("--baseline-run-id", required=True)
    run_compare.add_argument("--candidate-run-id", required=True)
    _select(run_compare, "eval.run.compare")

    attempt = commands.add_parser("attempt")
    attempt_commands = attempt.add_subparsers(
        dest="attempt_command",
        required=True,
    )
    attempt_get = attempt_commands.add_parser("get")
    attempt_get.add_argument("--attempt-id", required=True)
    _select(attempt_get, "eval.attempt.get")

    attempt_evidence = attempt_commands.add_parser("evidence")
    attempt_evidence.add_argument("--attempt-id", required=True)
    _select(attempt_evidence, "eval.attempt.evidence")

    execution = commands.add_parser("execution")
    execution_commands = execution.add_subparsers(
        dest="execution_command",
        required=True,
    )
    membership = execution_commands.add_parser("membership")
    membership.add_argument("--service-namespace")
    membership.add_argument("--service-name")
    membership.add_argument(
        "--executable-type",
        choices=tuple(item.value for item in ExecutableType),
        required=True,
    )
    membership.add_argument("--runtime-id", required=True)
    _add_pagination(membership)
    _select(membership, "eval.execution.membership")
    return parser


def _select(parser: argparse.ArgumentParser, command_path: str) -> None:
    parser.set_defaults(command_path=command_path)


def _add_pagination(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cursor")
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=50)


def _add_case_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--case-key", required=True)
    parser.add_argument(
        "--target-kind",
        choices=tuple(item.value for item in TargetKind),
        required=True,
    )
    parser.add_argument("--target-key", required=True)
    parser.add_argument("--input-version", type=int, required=True)
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a JSON input document, or - for standard input.",
    )
    parser.add_argument(
        "--expectation",
        help="Path to a JSON expectation document, or - for standard input.",
    )
    parser.add_argument("--evaluator-key", required=True)
    parser.add_argument("--evaluator-version", type=int, required=True)


def _case_values(arguments: argparse.Namespace) -> tuple[JsonValue, JsonValue | None]:
    if arguments.input == "-" and arguments.expectation == "-":
        raise CliUsageError("Input and expectation cannot both read standard input.")
    input_json = _read_json(arguments.input, label="input")
    expectation_json = None if arguments.expectation is None else _read_json(arguments.expectation, label="expectation")
    return input_json, expectation_json


def _read_json(location: str, *, label: str) -> JsonValue:
    try:
        raw = sys.stdin.read() if location == "-" else Path(location).read_text(encoding="utf-8")
    except OSError as error:
        raise CliUsageError(f"Unable to read the {label} JSON document.") from error
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise CliUsageError(f"The {label} document is not valid JSON.") from error


def _load_optional_harness(explicit: str | None) -> EvaluationHarness | None:
    locator = explicit or _pyproject_harness(required=False)
    return None if locator is None else _import_harness(locator)


def _load_harness(explicit: str | None) -> EvaluationHarness:
    locator = explicit or _pyproject_harness(required=True)
    assert locator is not None
    return _import_harness(locator)


def _import_harness(locator: str) -> EvaluationHarness:
    module_name, separator, object_name = locator.partition(":")
    if not separator or not module_name or not object_name or ":" in object_name:
        raise CliUsageError("The evaluation harness must use module:object syntax.")
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise CliUsageError(f"Unable to import evaluation harness module {module_name}.") from error
    try:
        harness = getattr(module, object_name)
    except AttributeError as error:
        raise CliUsageError(f"Evaluation harness object {object_name} does not exist in {module_name}.") from error
    if not isinstance(harness, EvaluationHarness):
        raise CliUsageError(f"{locator} must resolve to a junjo.evaluation.EvaluationHarness.")
    return harness


def _pyproject_harness(*, required: bool) -> str | None:
    for directory in (Path.cwd(), *Path.cwd().parents):
        path = directory / "pyproject.toml"
        if not path.is_file():
            continue
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
            locator = payload["tool"]["junjo"]["evaluation"]["harness"]
        except KeyError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise CliUsageError(f"Unable to read Junjo configuration from {path}.") from error
        if not isinstance(locator, str) or not locator.strip():
            raise CliUsageError(f"[tool.junjo.evaluation].harness in {path} must be a non-empty string.")
        return locator
    if required:
        raise CliUsageError(
            "Specify --harness module:object or configure [tool.junjo.evaluation].harness in pyproject.toml."
        )
    return None


def _studio_url(explicit: str | None) -> str:
    value = explicit or os.getenv("JUNJO_STUDIO_URL", DEFAULT_STUDIO_URL)
    if not value.strip():
        raise CliUsageError("JUNJO_STUDIO_URL cannot be empty.")
    return value


def _studio_token() -> str:
    token = os.getenv("JUNJO_AI_STUDIO_CLI_TOKEN")
    if token is None or not token.strip():
        raise CliUsageError("JUNJO_AI_STUDIO_CLI_TOKEN is required for evaluation control and queries.")
    return token


def _require_application(
    harness: EvaluationHarness,
    application_key: str,
) -> None:
    if application_key != harness.application_key:
        raise CliUsageError(f"Studio data belongs to {application_key}, not {harness.application_key}.")


def _harness_summary(
    harness: EvaluationHarness,
    *,
    include_targets: bool,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "application_key": harness.application_key,
        "service_identity": {
            "service_namespace": harness.service_identity.service_namespace,
            "service_name": harness.service_identity.service_name,
        },
    }
    if include_targets:
        summary["targets"] = [
            {
                "kind": descriptor.kind.value,
                "key": descriptor.key,
                "input_version": descriptor.input_version,
                "input_schema": descriptor.input_schema,
            }
            for descriptor in harness.target_descriptors()
        ]
    return summary


def _run_exit_code(detail: object) -> int:
    cases = getattr(detail, "cases", ())
    attempts = [item.attempt for item in cases]
    if any(attempt.status is AttemptStatus.ERROR for attempt in attempts):
        return EXIT_SUBJECT
    if any(attempt.status is AttemptStatus.FAILED for attempt in attempts):
        return EXIT_EVALUATION
    return EXIT_OK


def _emit_success(*, command: str, data: object) -> None:
    _write_json(
        {
            "schema_version": JSON_ENVELOPE_VERSION,
            "ok": True,
            "command": command,
            "data": data,
        }
    )


def _emit_error(
    *,
    command: str,
    code: str,
    message: str,
    exit_code: int,
) -> int:
    _write_json(
        {
            "schema_version": JSON_ENVELOPE_VERSION,
            "ok": False,
            "command": command,
            "error": {
                "code": code,
                "message": message,
            },
        }
    )
    print(f"{code}: {message}", file=sys.stderr)
    return exit_code


def _handle_error(*, command: str, error: BaseException) -> int:
    classifications: tuple[
        tuple[type[BaseException] | tuple[type[BaseException], ...], str, int],
        ...,
    ] = (
        (
            (CliUsageError, ValidationError, StudioValidationError),
            "usage_or_validation",
            EXIT_USAGE,
        ),
        (
            (StudioAuthenticationError, StudioAuthorizationError),
            "authentication",
            EXIT_AUTHENTICATION,
        ),
        (
            (StudioConflictError, ExecutionIdentityAmbiguous),
            "conflict",
            EXIT_CONFLICT,
        ),
        (
            (ExecutionEvidencePending, AttemptExecutionUnavailable),
            "pending_evidence",
            EXIT_PENDING_EVIDENCE,
        ),
        (StudioTransientError, "studio_unavailable", EXIT_TRANSIENT),
        (StudioContractError, "studio_contract", EXIT_CONTRACT),
        (
            (
                DirtySourceTreeError,
                EvaluatorContractError,
                EvaluatorNotRegisteredError,
                HarnessConfigurationError,
                RunComparisonError,
                TargetContractError,
                TargetNotRegisteredError,
            ),
            "evaluation_contract",
            EXIT_USAGE,
        ),
        (EvaluatorExecutionError, "evaluator_execution", EXIT_EVALUATION),
        (
            (CaseGenerationError, EvaluationRunError, TargetExecutionError),
            "subject_execution",
            EXIT_SUBJECT,
        ),
        (StudioRequestError, "studio_request", EXIT_INTERNAL),
    )
    for error_types, code, exit_code in classifications:
        if isinstance(error, error_types):
            return _emit_error(
                command=command,
                code=code,
                message=str(error),
                exit_code=exit_code,
            )
    return _emit_error(
        command=command,
        code="internal",
        message=f"Unexpected {type(error).__name__}.",
        exit_code=EXIT_INTERNAL,
    )


def _write_json(payload: Mapping[str, object]) -> None:
    print(
        json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value
