#!/usr/bin/env python3
"""Prove the installed Junjo evaluation loop against a disposable Studio.

The validator builds the current SDK wheel, installs it with the provider-free
standalone application, drives the public ``junjo eval`` CLI, exports real OTLP
telemetry, and queries the resulting Studio control records and trace evidence.

Studio must already be running. The target is treated as disposable because
evaluation datasets and Runs are intentionally immutable and have no delete
API. When Studio reports that setup is required, the shared local provisioner
creates the manual-test owner through the public first-user setup endpoint.
It then uses a random user, ingestion API key, and evaluation token for the
proof. Disposable credentials are cleaned afterward; credential values are
never command arguments or artifact content.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_agent_studio_e2e import (
    JsonClient,
    StudioE2EError,
    cleanup_test_identity,
    provision_test_identity,
    require,
    verify_owner_reauthentication,
    wait_for_health,
)

APPLICATION_KEY = "standalone_evaluation_example"
SERVICE_NAMESPACE = "junjo.examples"
SERVICE_NAME = "evaluation-standalone"
TARGETS = (
    ("node", "double.node", "Double Number Node"),
    ("workflow", "double.workflow", "Double Number Workflow"),
    ("agent", "double.agent", "Double Number Agent"),
)
EVALUATION_SCOPES = (
    "evaluation:read",
    "evaluation:write",
    "evidence:read",
)


@dataclass(frozen=True, slots=True)
class EvaluationCredential:
    """One scoped credential created and deleted by this proof."""

    id: str
    token: str


def _object(value: object, label: str) -> dict[str, Any]:
    require(
        isinstance(value, dict) and all(isinstance(key, str) for key in value),
        f"{label} must be an object",
    )
    return value


def _list(value: object, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label} must be a list")
    return value


def create_evaluation_credential(client: JsonClient) -> EvaluationCredential:
    """Create the exact control/query authority required by the public CLI."""

    created = _object(
        client.request(
            "/api/v1/evaluation-tokens",
            method="POST",
            body={
                "name": "Junjo Evaluation E2E",
                "scopes": list(EVALUATION_SCOPES),
            },
        ),
        "evaluation-token response",
    )
    token_id = created.get("id")
    token = created.get("token")
    require(
        isinstance(token_id, str) and bool(token_id),
        "Studio did not return an evaluation-token ID",
    )
    require(
        isinstance(token, str) and token.startswith("jcli_"),
        "Studio did not return an evaluation-token secret",
    )
    return EvaluationCredential(id=token_id, token=token)


def delete_evaluation_credential(
    client: JsonClient,
    credential: EvaluationCredential,
) -> None:
    """Delete the test credential through the human management boundary."""

    deleted = client.request(
        f"/api/v1/evaluation-tokens/{credential.id}",
        method="DELETE",
    )
    require(deleted is None, "Studio token deletion returned an unexpected response")


def build_installed_application(
    *,
    repository_root: Path,
    workspace: Path,
) -> tuple[Path, Path]:
    """Build the SDK wheel and install a clean independent application repo."""

    sdk_root = repository_root / "sdks/python"
    application_source = sdk_root / "examples/evaluation_standalone"
    application_root = workspace / "application"
    shutil.copytree(
        application_source,
        application_root,
        ignore=shutil.ignore_patterns(
            "build",
            "dist",
            "*.egg-info",
            "__pycache__",
            "*.pyc",
        ),
    )
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "Junjo E2E"],
        ["git", "config", "user.email", "junjo-e2e@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "Evaluation E2E application"],
    ):
        _run_build_command(
            command,
            cwd=application_root,
            label="standalone application Git fixture",
        )
    wheel_directory = workspace / "wheels"
    wheel_directory.mkdir()
    _run_build_command(
        [
            "uv",
            "build",
            "--wheel",
            "--project",
            str(sdk_root),
            "--out-dir",
            str(wheel_directory),
        ],
        cwd=repository_root,
        label="SDK wheel build",
    )
    wheels = tuple(wheel_directory.glob("junjo-*.whl"))
    require(len(wheels) == 1, "SDK wheel build did not produce exactly one wheel")

    environment_root = workspace / "venv"
    _run_build_command(
        [sys.executable, "-m", "venv", str(environment_root)],
        cwd=repository_root,
        label="isolated Python environment creation",
    )
    python = environment_root / "bin/python"
    pip = environment_root / "bin/pip"
    if os.name == "nt":
        python = environment_root / "Scripts/python.exe"
        pip = environment_root / "Scripts/pip.exe"
    _run_build_command(
        [
            str(pip),
            "install",
            "--disable-pip-version-check",
            str(wheels[0]),
        ],
        cwd=repository_root,
        label="SDK wheel installation",
    )
    _run_build_command(
        [
            str(pip),
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            str(application_root),
        ],
        cwd=repository_root,
        label="standalone application installation",
    )
    junjo = environment_root / "bin/junjo"
    if os.name == "nt":
        junjo = environment_root / "Scripts/junjo.exe"
    require(junjo.is_file(), "installed Junjo CLI is missing")
    require(python.is_file(), "isolated Python runtime is missing")
    return junjo, application_root


def _run_build_command(
    command: Sequence[str],
    *,
    cwd: Path,
    label: str,
) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise StudioE2EError(f"{label} failed") from error


def run_cli(
    junjo: Path,
    application_root: Path,
    environment: Mapping[str, str],
    arguments: Sequence[str],
    *,
    accepted_exit_codes: frozenset[int] = frozenset({0}),
) -> tuple[int, dict[str, Any]]:
    """Run one installed public command and parse its versioned JSON envelope."""

    try:
        completed = subprocess.run(
            [str(junjo), "eval", *arguments],
            cwd=application_root,
            env=dict(environment),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise StudioE2EError("the installed Junjo CLI could not start") from error
    try:
        envelope = _object(json.loads(completed.stdout), "Junjo CLI envelope")
    except json.JSONDecodeError as error:
        raise StudioE2EError("Junjo CLI did not return JSON") from error
    require(
        envelope.get("schema_version") == 1,
        "Junjo CLI envelope version changed",
    )
    if completed.returncode not in accepted_exit_codes:
        raw_error = envelope.get("error")
        error_detail = (
            _object(raw_error, "Junjo CLI error")
            if isinstance(raw_error, dict)
            else {
                "code": "unexpected_exit",
                "message": "Command returned a successful envelope.",
            }
        )
        raise StudioE2EError(
            f"Junjo CLI command {arguments[0]} failed with exit "
            f"{completed.returncode}: {error_detail.get('code')}: "
            f"{error_detail.get('message')}"
        )
    return completed.returncode, envelope


def command_data(envelope: Mapping[str, object]) -> dict[str, Any]:
    """Return the successful object payload of one CLI envelope."""

    require(envelope.get("ok") is True, "Junjo CLI command did not succeed")
    return _object(envelope.get("data"), "Junjo CLI data")


def add_authored_case(
    *,
    junjo: Path,
    application_root: Path,
    environment: Mapping[str, str],
    dataset_id: str,
    target_kind: str,
    target_key: str,
    case_key: str,
    input_path: Path,
    expectation_path: Path,
) -> dict[str, Any]:
    _, envelope = run_cli(
        junjo,
        application_root,
        environment,
        [
            "dataset",
            "add",
            "--dataset-id",
            dataset_id,
            "--case-key",
            case_key,
            "--evaluation-name",
            "Exact double result",
            "--target-kind",
            target_kind,
            "--target-key",
            target_key,
            "--input-version",
            "1",
            "--input",
            str(input_path),
            "--expectation",
            str(expectation_path),
            "--evaluator-key",
            "junjo.exact",
            "--evaluator-version",
            "1",
        ],
    )
    return command_data(envelope)


def poll_attempt_evidence(
    *,
    junjo: Path,
    application_root: Path,
    environment: Mapping[str, str],
    attempt_id: str,
    run_id: str,
    expected_status: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Wait for Studio's normal ingestion/indexing delay, then validate evidence."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        exit_code, envelope = run_cli(
            junjo,
            application_root,
            environment,
            ["attempt", "evidence", "--attempt-id", attempt_id],
            accepted_exit_codes=frozenset({0, 7}),
        )
        if exit_code == 0:
            data = command_data(envelope)
            assert_attempt_evidence(
                data,
                attempt_id=attempt_id,
                run_id=run_id,
                expected_status=expected_status,
            )
            return data
        if time.monotonic() >= deadline:
            raise StudioE2EError(
                "evaluation Attempt evidence did not become queryable before timeout"
            )
        time.sleep(1)


def assert_attempt_evidence(
    value: object,
    *,
    attempt_id: str,
    run_id: str,
    expected_status: str,
) -> None:
    """Validate evaluation classification and truthful application identity."""

    payload = _object(value, "Attempt evidence")
    attempt_detail = _object(payload.get("attempt"), "Attempt detail")
    attempt = _object(attempt_detail.get("attempt"), "Attempt")
    require(attempt.get("id") == attempt_id, "Attempt evidence identity changed")
    require(
        attempt.get("status") == expected_status,
        "deterministic Attempt status changed",
    )
    execution = _object(
        attempt.get("subject_execution"),
        "Attempt subject execution",
    )
    resolution = _object(payload.get("resolution"), "execution resolution")
    require(
        resolution.get("runtime_id") == execution.get("runtime_id"),
        "execution resolution runtime identity changed",
    )
    require(
        resolution.get("service_namespace") == SERVICE_NAMESPACE
        and resolution.get("service_name") == SERVICE_NAME,
        "evaluation evidence changed application service identity",
    )
    evidence = _object(payload.get("evidence"), "trace evidence")
    spans = _list(evidence.get("spans"), "trace spans")
    roles: set[str] = set()
    for raw_span in spans:
        span = _object(raw_span, "trace span")
        attributes = _object(span.get("attributes_json"), "trace span attributes")
        if attributes.get("junjo.evaluation.run.id") != run_id:
            continue
        require(
            attributes.get("junjo.evaluation.attempt.id") == attempt_id,
            "evaluation span carries the wrong Attempt identity",
        )
        require(
            attributes.get("junjo.evaluation.run_class") == "evaluation",
            "evaluation span carries the wrong run class",
        )
        role = attributes.get("junjo.evaluation.role")
        require(isinstance(role, str), "evaluation span role is missing")
        roles.add(role)
        resource = _object(
            span.get("resource_attributes_json"),
            "trace span Resource",
        )
        require(
            resource.get("service.namespace") == SERVICE_NAMESPACE
            and resource.get("service.name") == SERVICE_NAME,
            "evaluation span Resource changed application identity",
        )
    require(
        {"orchestrator", "subject"}.issubset(roles),
        "evaluation trace is missing orchestration or subject role spans",
    )


def service_span_count(client: JsonClient) -> int:
    """Return the bounded number of currently queryable standalone spans."""

    service = urllib.parse.quote(SERVICE_NAME, safe="")
    spans = _list(
        client.request(f"/api/v1/observability/services/{service}/spans?limit=250"),
        "service spans",
    )
    return len(spans)


def execute_proof(
    *,
    backend_url: str,
    ingestion_host: str,
    ingestion_port: int,
    timeout_seconds: float,
    repository_root: Path,
    evidence_output: Path,
) -> None:
    """Run the complete installed SDK -> Studio evaluation proof."""

    backend = JsonClient(backend_url)
    wait_for_health(
        backend,
        timeout_seconds=timeout_seconds,
        interval_seconds=1,
    )
    identity = provision_test_identity(backend)
    credential: EvaluationCredential | None = None
    cleanup_error: BaseException | None = None
    try:
        credential = create_evaluation_credential(backend)
        with tempfile.TemporaryDirectory(
            prefix="junjo-evaluation-e2e-"
        ) as raw_workspace:
            workspace = Path(raw_workspace)
            junjo, application_root = build_installed_application(
                repository_root=repository_root,
                workspace=workspace,
            )
            input_path = workspace / "input.json"
            expectation_path = workspace / "expectation.json"
            input_path.write_text('{"value": 2}\n', encoding="utf-8")
            expectation_path.write_text('{"expected": 4}\n', encoding="utf-8")
            environment = {
                **os.environ,
                "JUNJO_AI_STUDIO_BACKEND_BASE_URL": backend_url,
                "JUNJO_AI_STUDIO_CLI_TOKEN": credential.token,
                "JUNJO_AI_STUDIO_API_KEY": identity.api_key,
                "JUNJO_AI_STUDIO_OTLP_ENDPOINT": f"{ingestion_host}:{ingestion_port}",
                "JUNJO_AI_STUDIO_OTLP_INSECURE": "true",
            }

            _, targets_envelope = run_cli(
                junjo,
                application_root,
                environment,
                ["targets", "list"],
            )
            targets = _list(
                command_data(targets_envelope).get("targets"),
                "target descriptors",
            )
            require(
                {
                    (
                        _object(item, "target descriptor").get("kind"),
                        _object(item, "target descriptor").get("key"),
                        _object(item, "target descriptor").get("name"),
                    )
                    for item in targets
                }
                == set(TARGETS),
                "installed application target declarations changed",
            )
            _, evaluators_envelope = run_cli(
                junjo,
                application_root,
                environment,
                ["evaluators", "list"],
            )
            evaluators = _list(
                command_data(evaluators_envelope).get("evaluators"),
                "evaluator descriptors",
            )
            require(len(evaluators) == 1, "installed evaluator declarations changed")
            evaluator = _object(evaluators[0], "evaluator descriptor")
            expectation_schema = _object(
                evaluator.get("expectation_schema"),
                "evaluator expectation schema",
            )
            require(
                evaluator.get("key") == "junjo.exact"
                and evaluator.get("version") == 1
                and evaluator.get("role") == "verifier"
                and expectation_schema.get("additionalProperties") is False,
                "installed evaluator descriptor changed",
            )

            _, dataset_envelope = run_cli(
                junjo,
                application_root,
                environment,
                [
                    "dataset",
                    "create",
                    "--key",
                    "evaluation-e2e",
                    "--name",
                    "Evaluation E2E",
                ],
            )
            dataset = command_data(dataset_envelope)
            dataset_id = dataset.get("id")
            require(isinstance(dataset_id, str), "dataset ID is missing")

            _, generated_envelope = run_cli(
                junjo,
                application_root,
                environment,
                [
                    "case",
                    "generate",
                    "--dataset-id",
                    dataset_id,
                    "--case-key",
                    "double-node",
                    "--evaluation-name",
                    "Exact double result",
                    "--target-kind",
                    "node",
                    "--target-key",
                    "double.node",
                    "--input-version",
                    "1",
                    "--input",
                    str(input_path),
                    "--expectation",
                    str(expectation_path),
                    "--evaluator-key",
                    "junjo.exact",
                    "--evaluator-version",
                    "1",
                ],
            )
            generated_case = command_data(generated_envelope)
            require(
                generated_case.get("origin") == "generated"
                and generated_case.get("target_name") == TARGETS[0][2]
                and isinstance(generated_case.get("source_execution"), dict),
                "generated Case did not retain its target name and source execution",
            )

            case_ids = [generated_case.get("id")]
            for target_kind, target_key, target_name in TARGETS[1:]:
                case = add_authored_case(
                    junjo=junjo,
                    application_root=application_root,
                    environment=environment,
                    dataset_id=dataset_id,
                    target_kind=target_kind,
                    target_key=target_key,
                    case_key=f"double-{target_kind}",
                    input_path=input_path,
                    expectation_path=expectation_path,
                )
                require(
                    case.get("target_name") == target_name,
                    "authored Case did not retain its target name",
                )
                case_ids.append(case.get("id"))
            require(
                all(isinstance(case_id, str) for case_id in case_ids),
                "one or more Case IDs are missing",
            )

            repeated = add_authored_case(
                junjo=junjo,
                application_root=application_root,
                environment=environment,
                dataset_id=dataset_id,
                target_kind="workflow",
                target_key="double.workflow",
                case_key="double-workflow",
                input_path=input_path,
                expectation_path=expectation_path,
            )
            require(
                repeated.get("id") == case_ids[1],
                "natural Case idempotency returned a different record",
            )

            run_cli(
                junjo,
                application_root,
                environment,
                ["dataset", "lock", "--dataset-id", dataset_id],
            )

            run_details: list[dict[str, Any]] = []
            for request_key, run_label in (
                ("baseline", "baseline"),
                ("candidate", "candidate"),
            ):
                command_environment = dict(environment)
                expected_statuses = ["passed", "passed", "passed"]
                accepted_exit_codes = frozenset({0})
                if run_label == "candidate":
                    command_environment["JUNJO_EVALUATION_EXAMPLE_AGENT_FACTOR"] = "3"
                    expected_statuses[-1] = "failed"
                    accepted_exit_codes = frozenset({6})
                _, run_envelope = run_cli(
                    junjo,
                    application_root,
                    command_environment,
                    [
                        "run",
                        "execute",
                        "--dataset-id",
                        dataset_id,
                        "--request-key",
                        request_key,
                        "--run-label",
                        run_label,
                    ],
                    accepted_exit_codes=accepted_exit_codes,
                )
                detail = command_data(run_envelope)
                run = _object(detail.get("run"), "Run")
                require(
                    run.get("status") == "completed", "evaluation Run did not complete"
                )
                attempts = [
                    _object(_object(item, "Run Case").get("attempt"), "Attempt")
                    for item in _list(detail.get("cases"), "Run Cases")
                ]
                require(
                    len(attempts) == 3
                    and [attempt.get("status") for attempt in attempts]
                    == expected_statuses,
                    "deterministic evaluation Attempt outcomes changed",
                )
                run_details.append(detail)
                run_id = run.get("id")
                require(isinstance(run_id, str), "Run ID is missing")
                for attempt, expected_status in zip(
                    attempts,
                    expected_statuses,
                    strict=True,
                ):
                    attempt_id = attempt.get("id")
                    require(isinstance(attempt_id, str), "Attempt ID is missing")
                    poll_attempt_evidence(
                        junjo=junjo,
                        application_root=application_root,
                        environment=environment,
                        attempt_id=attempt_id,
                        run_id=run_id,
                        expected_status=expected_status,
                        timeout_seconds=timeout_seconds,
                    )

            baseline_run = _object(run_details[0].get("run"), "baseline Run")
            candidate_run = _object(run_details[-1].get("run"), "candidate Run")
            baseline_run_id = baseline_run.get("id")
            candidate_run_id = candidate_run.get("id")
            require(
                isinstance(baseline_run_id, str) and isinstance(candidate_run_id, str),
                "comparison Run identities are missing",
            )
            _, comparison_envelope = run_cli(
                junjo,
                application_root,
                environment,
                [
                    "run",
                    "compare",
                    "--baseline-run-id",
                    baseline_run_id,
                    "--candidate-run-id",
                    candidate_run_id,
                ],
            )
            comparison = command_data(comparison_envelope)
            transition_counts = _object(
                comparison.get("transition_counts"),
                "comparison transition counts",
            )
            require(
                len(_list(comparison.get("rows"), "comparison rows")) == 3
                and transition_counts.get("regressed") == 1
                and transition_counts.get("unchanged") == 2,
                "Run comparison did not align all Cases",
            )
            _, scoped_comparison_envelope = run_cli(
                junjo,
                application_root,
                environment,
                [
                    "run",
                    "compare",
                    "--baseline-run-id",
                    baseline_run_id,
                    "--candidate-run-id",
                    candidate_run_id,
                    "--target-kind",
                    "agent",
                    "--target-key",
                    "double.agent",
                    "--input-version",
                    "1",
                    "--evaluation-name",
                    "Exact double result",
                ],
            )
            scoped_comparison = command_data(scoped_comparison_envelope)
            scoped_transitions = _object(
                scoped_comparison.get("transition_counts"),
                "scoped comparison transition counts",
            )
            require(
                len(_list(scoped_comparison.get("rows"), "scoped comparison rows")) == 1
                and scoped_transitions.get("regressed") == 1,
                "Run comparison did not retain the exact Agent scope",
            )
            _, scoped_runs_envelope = run_cli(
                junjo,
                application_root,
                environment,
                [
                    "run",
                    "list",
                    "--dataset-id",
                    dataset_id,
                    "--target-kind",
                    "agent",
                    "--target-key",
                    "double.agent",
                    "--input-version",
                    "1",
                    "--evaluation-name",
                    "Exact double result",
                ],
            )
            scoped_runs = command_data(scoped_runs_envelope)
            scoped_items = _list(scoped_runs.get("items"), "scoped Run items")
            require(len(scoped_items) == 2, "scoped Run history changed")
            candidate_item = next(
                (
                    _object(item, "scoped Run item")
                    for item in scoped_items
                    if _object(item, "scoped Run item").get("run", {}).get("id")
                    == candidate_run_id
                ),
                None,
            )
            require(candidate_item is not None, "scoped candidate Run is missing")
            assert candidate_item is not None
            candidate_summary = _object(
                candidate_item.get("outcome_summary"),
                "scoped outcome summary",
            )
            require(
                candidate_summary.get("total") == 1
                and candidate_summary.get("failed") == 1
                and candidate_summary.get("pass_rate") == 0.0
                and candidate_summary.get("coverage") == 1.0,
                "scoped candidate outcome summary changed",
            )

            spans_before_resume = service_span_count(backend)
            _, resume_envelope = run_cli(
                junjo,
                application_root,
                environment,
                ["run", "resume", "--run-id", candidate_run_id],
                accepted_exit_codes=frozenset({6}),
            )
            resumed = command_data(resume_envelope)
            require(
                _object(resumed.get("run"), "resumed Run").get("id")
                == candidate_run_id,
                "resume returned a different Run",
            )
            time.sleep(1)
            require(
                service_span_count(backend) == spans_before_resume,
                "resuming a completed Run emitted new application telemetry",
            )

            evidence_output.parent.mkdir(parents=True, exist_ok=True)
            evidence_output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "application_key": APPLICATION_KEY,
                        "dataset_id": dataset_id,
                        "baseline_run_id": baseline_run_id,
                        "candidate_run_id": candidate_run_id,
                        "case_count": 3,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            delete_evaluation_credential(backend, credential)
            credential = None
            exit_code, envelope = run_cli(
                junjo,
                application_root,
                environment,
                ["run", "get", "--run-id", candidate_run_id],
                accepted_exit_codes=frozenset({3}),
            )
            require(
                exit_code == 3
                and envelope.get("ok") is False
                and _object(envelope.get("error"), "CLI error").get("code")
                == "authentication",
                "deleted evaluation token remained authorized",
            )
    finally:
        if credential is not None:
            try:
                delete_evaluation_credential(backend, credential)
            except BaseException as error:
                cleanup_error = error
        try:
            cleanup_test_identity(backend, identity)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
            else:
                print(
                    f"warning: Studio identity cleanup also failed: {error}",
                    file=sys.stderr,
                )
    if cleanup_error is not None:
        raise cleanup_error
    verify_owner_reauthentication(backend)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--ingestion-host", required=True)
    parser.add_argument("--ingestion-port", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--evidence-output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    require(arguments.timeout_seconds > 0, "--timeout-seconds must be positive")
    require(
        1 <= arguments.ingestion_port <= 65_535,
        "--ingestion-port must be valid",
    )
    execute_proof(
        backend_url=arguments.backend_url,
        ingestion_host=arguments.ingestion_host,
        ingestion_port=arguments.ingestion_port,
        timeout_seconds=arguments.timeout_seconds,
        repository_root=arguments.repository_root.resolve(),
        evidence_output=arguments.evidence_output.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
