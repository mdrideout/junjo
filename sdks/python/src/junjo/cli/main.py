"""JSON-first command line interface for Junjo evaluation workflows."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import sysconfig
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, Literal, NoReturn

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
    AttemptEvidenceUnavailable,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    DatasetCreate,
    ExecutableType,
    ExecutionEvidencePending,
    ExecutionIdentityAmbiguous,
    OpenTelemetrySpanReference,
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
from .interface import (
    DEFAULT_STUDIO_BACKEND_BASE_URL,
    EVALUATION_CONFIG,
    EVIDENCE_ACCESS_LEVELS,
    CommandMetadata,
    build_evaluation_interface,
    render_evaluation_interface_markdown,
)

JSON_ENVELOPE_VERSION = 1

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
    output_format: Literal["json", "markdown"] = "json"


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

    if result.output_format == "markdown":
        print(result.data)
    else:
        _emit_success(command=command, data=result.data)
    return result.exit_code


async def _dispatch(arguments: argparse.Namespace) -> CommandResult:
    command = arguments.command_path
    if command == "eval.explain":
        interface = build_evaluation_interface(_parser())
        if arguments.format == "json":
            return CommandResult(interface)
        return CommandResult(
            render_evaluation_interface_markdown(interface),
            output_format="markdown",
        )
    if command == "eval.skill.path":
        skill_directory = _skill_directory(arguments.name)
        return CommandResult(
            {
                "name": arguments.name,
                "path": str(skill_directory),
                "skill_file": str(skill_directory / "SKILL.md"),
            }
        )
    if command == "eval.capabilities":
        harness = _load_optional_harness(arguments.harness)
        async with StudioClient(base_url=_studio_backend_base_url(arguments.studio_backend_base_url)) as client:
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
            "agent_guidance": {
                "skill_name": "junjo-evaluation",
                "skill_discovery_command": "junjo eval skill path",
                "interface_explainer_command": "junjo eval explain",
                "interface_explainer_json_command": "junjo eval explain --format json",
            },
            "evidence_access": EVIDENCE_ACCESS_LEVELS,
        }
        if harness is not None:
            data["application"] = _harness_summary(
                harness,
                include_targets=False,
                include_evaluators=False,
            )
        return CommandResult(data)

    harness = _load_harness(arguments.harness)
    if command == "eval.targets.list":
        return CommandResult(
            _harness_summary(
                harness,
                include_targets=True,
                include_evaluators=False,
            )
        )
    if command == "eval.evaluators.list":
        return CommandResult(
            _harness_summary(
                harness,
                include_targets=False,
                include_evaluators=True,
            )
        )

    token = _studio_token()
    async with StudioClient(
        base_url=_studio_backend_base_url(arguments.studio_backend_base_url),
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
    if command == "eval.evidence.membership":
        return await _evidence_membership(
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
        target, _, _, _ = harness.validate_case_contract(
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
                    evaluation_name=arguments.evaluation_name,
                    origin=CaseOrigin.AUTHORED,
                    target_kind=target_kind,
                    target_key=arguments.target_key,
                    target_name=target.name,
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
                    evaluation_name=arguments.evaluation_name,
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
                    run_label=arguments.run_label,
                )
            else:
                detail = await executor.resume(run_id=arguments.run_id)
        return CommandResult(detail, _run_exit_code(detail))
    if command == "eval.run.list":
        page = await client.list_runs(
            dataset_id=arguments.dataset_id,
            target_kind=(TargetKind(arguments.target_kind) if arguments.target_kind is not None else None),
            target_key=arguments.target_key,
            input_version=arguments.input_version,
            evaluation_name=arguments.evaluation_name,
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
            target_kind=(TargetKind(arguments.target_kind) if arguments.target_kind is not None else None),
            target_key=arguments.target_key,
            input_version=arguments.input_version,
            evaluation_name=arguments.evaluation_name,
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
    if command == "eval.attempt.evidence.full":
        evidence = await client.get_attempt_evidence(arguments.attempt_id)
        _require_application(harness, evidence.attempt.dataset.application_key)
        return CommandResult(evidence)
    if command in {
        "eval.attempt.evidence.manifest",
        "eval.attempt.evidence.spans",
    }:
        attempt = await client.get_attempt(arguments.attempt_id)
        _require_application(harness, attempt.dataset.application_key)
        if command == "eval.attempt.evidence.manifest":
            return CommandResult(await client.get_attempt_evidence_manifest(arguments.attempt_id))
        return CommandResult(
            await client.get_attempt_evidence_spans(
                arguments.attempt_id,
                arguments.span_id,
            )
        )
    raise AssertionError(f"Unhandled attempt command {command}.")


async def _evidence_membership(
    arguments: argparse.Namespace,
    *,
    client: StudioClient,
    harness: EvaluationHarness,
) -> CommandResult:
    service_namespace = (
        harness.service_identity.service_namespace
        if arguments.service_namespace is None
        else arguments.service_namespace
    )
    service_name = harness.service_identity.service_name if arguments.service_name is None else arguments.service_name
    if arguments.kind == "junjo_execution":
        if arguments.executable_type is None or arguments.runtime_id is None:
            raise CliUsageError("junjo_execution evidence requires --executable-type and --runtime-id.")
        if arguments.trace_id is not None or arguments.span_id is not None:
            raise CliUsageError("junjo_execution evidence does not accept --trace-id or --span-id.")
        reference = SemanticExecutionReference(
            service_namespace=service_namespace,
            service_name=service_name,
            executable_type=ExecutableType(arguments.executable_type),
            runtime_id=arguments.runtime_id,
        )
    else:
        if arguments.trace_id is None or arguments.span_id is None:
            raise CliUsageError("otel_span evidence requires --trace-id and --span-id.")
        if arguments.executable_type is not None or arguments.runtime_id is not None:
            raise CliUsageError("otel_span evidence does not accept --executable-type or --runtime-id.")
        reference = OpenTelemetrySpanReference(
            service_namespace=service_namespace,
            service_name=service_name,
            trace_id=arguments.trace_id,
            span_id=arguments.span_id,
        )
    return CommandResult(
        await client.get_evidence_membership(
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
    harness_config, base_url_config, _ = EVALUATION_CONFIG
    evaluation.add_argument(
        "--harness",
        help=f"{harness_config.purpose} Overrides {harness_config.pyproject}.",
    )
    evaluation.add_argument(
        "--studio-backend-base-url",
        help=(
            f"{base_url_config.purpose} Overrides {base_url_config.environment}; default: {base_url_config.default}."
        ),
    )
    commands = evaluation.add_subparsers(dest="eval_command", required=True)

    skill = _group(
        commands,
        "skill",
        summary="Locate coding-agent guidance shipped with this Junjo installation.",
    )
    skill_commands = skill.add_subparsers(dest="skill_command", required=True)
    skill_path = _command(
        skill_commands,
        "path",
        command_path="eval.skill.path",
        summary="Return the local path to an installed Junjo coding-agent skill.",
        authentication="none",
        harness="not_used",
        executes_evaluation_target=False,
        response="SkillPath",
    )
    skill_path.add_argument(
        "--name",
        choices=("junjo-evaluation", "junjo-openai-agents"),
        default="junjo-evaluation",
        help="Installed Junjo skill to locate (default: junjo-evaluation).",
    )

    _command(
        commands,
        "capabilities",
        command_path="eval.capabilities",
        summary="Inspect compatible SDK, Studio, agent-guidance, and evidence interfaces.",
        authentication="none",
        harness="optional",
        executes_evaluation_target=False,
        response="EvaluationCapabilities",
    )

    explain = _command(
        commands,
        "explain",
        command_path="eval.explain",
        summary="Explain every evaluation command, configuration source, and evidence level.",
        authentication="none",
        harness="not_used",
        executes_evaluation_target=False,
        response="Markdown by default; EvaluationCliInterface with --format json",
    )
    explain.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Render readable Markdown or a machine-readable JSON contract (default: markdown).",
    )

    targets = _group(
        commands,
        "targets",
        summary="Inspect evaluation targets declared by the application harness.",
    )
    target_commands = targets.add_subparsers(dest="targets_command", required=True)
    _command(
        target_commands,
        "list",
        command_path="eval.targets.list",
        summary="List Node, Workflow, and Agent targets with their input schemas.",
        authentication="none",
        harness="required",
        executes_evaluation_target=False,
        response="ApplicationTargetList",
    )

    evaluators = _group(
        commands,
        "evaluators",
        summary="Inspect evaluators declared by the application harness.",
    )
    evaluator_commands = evaluators.add_subparsers(
        dest="evaluators_command",
        required=True,
    )
    _command(
        evaluator_commands,
        "list",
        command_path="eval.evaluators.list",
        summary="List evaluators with their roles and expectation schemas.",
        authentication="none",
        harness="required",
        executes_evaluation_target=False,
        response="ApplicationEvaluatorList",
    )

    dataset = _group(
        commands,
        "dataset",
        summary="Create, inspect, populate, and lock Studio evaluation datasets.",
    )
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_create = _studio_command(
        dataset_commands,
        "create",
        command_path="eval.dataset.create",
        summary="Create or retrieve an application-scoped dataset by its stable key.",
        response="DatasetRead",
    )
    dataset_create.add_argument("--key", required=True, help="Stable application-owned dataset key.")
    dataset_create.add_argument("--name", required=True, help="Human-readable dataset name.")
    dataset_create.add_argument("--description", help="Optional human-readable dataset purpose.")

    dataset_list = _studio_command(
        dataset_commands,
        "list",
        command_path="eval.dataset.list",
        summary="List one bounded page of datasets owned by this application.",
        response="DatasetList",
    )
    _add_pagination(dataset_list)

    dataset_get = _studio_command(
        dataset_commands,
        "get",
        command_path="eval.dataset.get",
        summary="Get one dataset and its complete bounded Case membership.",
        response="DatasetDetail",
    )
    _add_id_argument(dataset_get, "--dataset-id", "Dataset record ID.")

    dataset_add = _studio_command(
        dataset_commands,
        "add",
        command_path="eval.dataset.add",
        summary="Add one authored Case to a draft dataset after local contract validation.",
        response="CaseRead",
    )
    _add_case_arguments(dataset_add)

    dataset_lock = _studio_command(
        dataset_commands,
        "lock",
        command_path="eval.dataset.lock",
        summary="Validate every Case locally and permanently lock a dataset for runs.",
        response="DatasetRead",
    )
    _add_id_argument(dataset_lock, "--dataset-id", "Draft dataset record ID.")

    case = _group(
        commands,
        "case",
        summary="Generate dataset Cases by executing real application targets.",
    )
    case_commands = case.add_subparsers(dest="case_command", required=True)
    case_generate = _studio_command(
        case_commands,
        "generate",
        command_path="eval.case.generate",
        summary="Execute one target and save its input plus exact source evidence as a generated Case.",
        response="CaseRead",
        executes_evaluation_target=True,
    )
    _add_case_arguments(case_generate)

    run = _group(
        commands,
        "run",
        summary="Execute, resume, inspect, and compare locked evaluation runs.",
    )
    run_commands = run.add_subparsers(dest="run_command", required=True)
    run_execute = _studio_command(
        run_commands,
        "execute",
        command_path="eval.run.execute",
        summary="Execute every Case in a locked dataset as one labeled source revision.",
        response="RunDetail",
        executes_evaluation_target=True,
    )
    _add_id_argument(run_execute, "--dataset-id", "Locked dataset record ID.")
    run_execute.add_argument(
        "--request-key",
        required=True,
        help="Stable idempotency key for this requested run.",
    )
    run_execute.add_argument("--run-label", required=True, help="Human-readable run label.")

    run_resume = _studio_command(
        run_commands,
        "resume",
        command_path="eval.run.resume",
        summary="Continue queued Attempts in an existing run using the current application source.",
        response="RunDetail",
        executes_evaluation_target=True,
    )
    _add_id_argument(run_resume, "--run-id", "Evaluation run record ID.")

    run_list = _studio_command(
        run_commands,
        "list",
        command_path="eval.run.list",
        summary="List one bounded page of run summaries using conjunctive Case-scope filters.",
        response="RunList",
    )
    _add_id_argument(run_list, "--dataset-id", "Dataset record ID used to scope run history.")
    run_list.add_argument(
        "--target-kind",
        choices=tuple(item.value for item in TargetKind),
        help="Optionally restrict results to Cases with this target kind.",
    )
    run_list.add_argument("--target-key", help="Optionally restrict results to this target key.")
    run_list.add_argument(
        "--input-version",
        type=int,
        help="Optionally restrict results to this target input contract version.",
    )
    run_list.add_argument(
        "--evaluation-name",
        help="Optionally restrict results to Cases with this evaluation name.",
    )
    _add_pagination(run_list)

    run_get = _studio_command(
        run_commands,
        "get",
        command_path="eval.run.get",
        summary="Get one run with its locked dataset and complete Case/Attempt membership.",
        response="RunDetail",
    )
    _add_id_argument(run_get, "--run-id", "Evaluation run record ID.")

    run_compare = _studio_command(
        run_commands,
        "compare",
        command_path="eval.run.compare",
        summary="Compare aligned binary outcomes from two runs of the same locked dataset.",
        response="RunComparison",
    )
    _add_id_argument(run_compare, "--baseline-run-id", "Baseline evaluation run record ID.")
    _add_id_argument(run_compare, "--candidate-run-id", "Candidate evaluation run record ID.")
    run_compare.add_argument(
        "--target-kind",
        choices=tuple(item.value for item in TargetKind),
        help="Optionally compare only Cases with this target kind.",
    )
    run_compare.add_argument("--target-key", help="Optionally compare only this target key.")
    run_compare.add_argument(
        "--input-version",
        type=int,
        help="Optionally compare only this target input contract version.",
    )
    run_compare.add_argument(
        "--evaluation-name",
        help="Optionally compare only Cases with this evaluation name.",
    )

    attempt = _group(
        commands,
        "attempt",
        summary="Inspect one Case Attempt and hydrate its evidence in explicit stages.",
    )
    attempt_commands = attempt.add_subparsers(
        dest="attempt_command",
        required=True,
    )
    attempt_get = _studio_command(
        attempt_commands,
        "get",
        command_path="eval.attempt.get",
        summary="Get bounded control context for one Attempt without hydrating trace evidence.",
        response="AttemptDetail",
        evidence_level="attempt_summary",
    )
    _add_id_argument(attempt_get, "--attempt-id", "Evaluation Attempt record ID.")

    attempt_evidence = _group(
        attempt_commands,
        "evidence",
        summary="Hydrate one Attempt's trace evidence at an explicit level.",
    )
    attempt_evidence_commands = attempt_evidence.add_subparsers(
        dest="attempt_evidence_command",
        required=True,
    )
    manifest = _studio_command(
        attempt_evidence_commands,
        "manifest",
        command_path="eval.attempt.evidence.manifest",
        summary="Get bounded execution structure, failures, integrity, and selectable span IDs.",
        response="AttemptEvidenceManifest",
        evidence_level="manifest",
    )
    _add_id_argument(manifest, "--attempt-id", "Evaluation Attempt record ID.")

    spans = _studio_command(
        attempt_evidence_commands,
        "spans",
        command_path="eval.attempt.evidence.spans",
        summary="Get complete evidence for explicitly selected spans in the Attempt trace.",
        response="AttemptEvidenceSpans",
        evidence_level="selected_spans",
    )
    _add_id_argument(spans, "--attempt-id", "Evaluation Attempt record ID.")
    spans.add_argument(
        "--span-id",
        action="append",
        required=True,
        help="Exact 16-character lowercase hexadecimal span ID; repeat for each selected span.",
    )

    full = _studio_command(
        attempt_evidence_commands,
        "full",
        command_path="eval.attempt.evidence.full",
        summary="Get complete lossless trace evidence and all semantic annotations for an Attempt.",
        response="AttemptEvidence",
        evidence_level="full",
    )
    _add_id_argument(full, "--attempt-id", "Evaluation Attempt record ID.")

    evidence = _group(
        commands,
        "evidence",
        summary="Find datasets and Attempts that reference an exact execution identity.",
    )
    evidence_commands = evidence.add_subparsers(
        dest="evidence_command",
        required=True,
    )
    membership = _studio_command(
        evidence_commands,
        "membership",
        command_path="eval.evidence.membership",
        summary="Find one bounded page of Case-source or Attempt-subject memberships.",
        response="EvidenceMembershipList",
    )
    membership.add_argument(
        "--kind",
        choices=("junjo_execution", "otel_span"),
        required=True,
        help="Semantic Junjo execution identity or exact OpenTelemetry span identity.",
    )
    membership.add_argument(
        "--service-namespace",
        help="Override the application harness service namespace.",
    )
    membership.add_argument("--service-name", help="Override the application harness service name.")
    membership.add_argument(
        "--executable-type",
        choices=tuple(item.value for item in ExecutableType),
        help="Required only for junjo_execution evidence.",
    )
    membership.add_argument("--runtime-id", help="Required only for junjo_execution evidence.")
    membership.add_argument("--trace-id", help="Required only for otel_span evidence.")
    membership.add_argument("--span-id", help="Required only for otel_span evidence.")
    _add_pagination(membership)
    return parser


def _group(
    subparsers: argparse._SubParsersAction[JsonArgumentParser],
    name: str,
    *,
    summary: str,
) -> JsonArgumentParser:
    return subparsers.add_parser(name, help=summary, description=summary)


def _command(
    subparsers: argparse._SubParsersAction[JsonArgumentParser],
    name: str,
    *,
    command_path: str,
    summary: str,
    authentication: str,
    harness: str,
    executes_evaluation_target: bool,
    response: str,
    evidence_level: str | None = None,
) -> JsonArgumentParser:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    metadata = CommandMetadata(
        path=command_path,
        summary=summary,
        authentication=authentication,
        harness=harness,
        executes_evaluation_target=executes_evaluation_target,
        response=response,
        evidence_level=evidence_level,
    )
    parser.set_defaults(command_path=command_path, _command_metadata=metadata)
    return parser


def _studio_command(
    subparsers: argparse._SubParsersAction[JsonArgumentParser],
    name: str,
    *,
    command_path: str,
    summary: str,
    response: str,
    executes_evaluation_target: bool = False,
    evidence_level: str | None = None,
) -> JsonArgumentParser:
    return _command(
        subparsers,
        name,
        command_path=command_path,
        summary=summary,
        authentication="JUNJO_AI_STUDIO_CLI_TOKEN",
        harness="required",
        executes_evaluation_target=executes_evaluation_target,
        response=response,
        evidence_level=evidence_level,
    )


def _add_id_argument(parser: argparse.ArgumentParser, flag: str, help_text: str) -> None:
    parser.add_argument(flag, required=True, help=help_text)


def _add_pagination(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cursor", help="Opaque cursor returned by the preceding page.")
    parser.add_argument(
        "--limit",
        type=int,
        choices=range(1, 101),
        default=50,
        help="Maximum records in this bounded page (default: 50).",
    )


def _add_case_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id_argument(parser, "--dataset-id", "Draft dataset record ID.")
    parser.add_argument("--case-key", required=True, help="Stable Case identity within the dataset.")
    parser.add_argument(
        "--evaluation-name",
        required=True,
        help="Human-readable product claim this Case evaluates.",
    )
    parser.add_argument(
        "--target-kind",
        choices=tuple(item.value for item in TargetKind),
        required=True,
        help="Junjo execution scope exercised by this Case.",
    )
    parser.add_argument("--target-key", required=True, help="Application-declared target key.")
    parser.add_argument(
        "--input-version",
        type=int,
        required=True,
        help="Application-declared target input contract version.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a JSON input document, or - for standard input.",
    )
    parser.add_argument(
        "--expectation",
        help="Path to a JSON expectation document, or - for standard input.",
    )
    parser.add_argument("--evaluator-key", required=True, help="Application-declared evaluator key.")
    parser.add_argument(
        "--evaluator-version",
        type=int,
        required=True,
        help="Application-declared evaluator contract version.",
    )


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


def _skill_directory(name: str) -> Path:
    installed = Path(sysconfig.get_path("data")) / "share" / "junjo" / "skills" / name
    source_checkout = Path(__file__).resolve().parents[3] / "skills" / name
    for candidate in (installed, source_checkout):
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    raise CliUsageError(f"This Junjo installation does not contain the {name} skill.")


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


def _studio_backend_base_url(explicit: str | None) -> str:
    value = explicit or os.getenv(
        "JUNJO_AI_STUDIO_BACKEND_BASE_URL",
        DEFAULT_STUDIO_BACKEND_BASE_URL,
    )
    if not value.strip():
        raise CliUsageError("JUNJO_AI_STUDIO_BACKEND_BASE_URL cannot be empty.")
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
    include_evaluators: bool,
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
                "name": descriptor.name,
                "input_version": descriptor.input_version,
                "input_schema": descriptor.input_schema,
            }
            for descriptor in harness.target_descriptors()
        ]
    if include_evaluators:
        summary["evaluators"] = [
            {
                "key": descriptor.key,
                "version": descriptor.version,
                "role": descriptor.role.value,
                "expectation_schema": descriptor.expectation_schema,
            }
            for descriptor in harness.evaluator_descriptors()
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
            (ExecutionEvidencePending, AttemptEvidenceUnavailable),
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
