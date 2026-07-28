"""Cross-component proof that SDK DTOs match Studio's versioned OpenAPI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from junjo.studio import (
    AttemptCounts,
    AttemptDetail,
    AttemptExecutionBind,
    AttemptRead,
    AttemptResultWrite,
    CaseCreate,
    CaseRead,
    ConflictResponse,
    DatasetCreate,
    DatasetDetail,
    DatasetList,
    DatasetRead,
    DatasetSummary,
    ExecutionMembershipItem,
    ExecutionMembershipList,
    ExecutionResolutionConflict,
    ExecutionResolutionRead,
    RunCaseRead,
    RunDetail,
    RunList,
    RunRead,
    RunStart,
    RunSummary,
    SemanticExecutionReference,
    StudioHealth,
    TargetKind,
    TraceEvidenceRead,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = REPO_ROOT / "apps/studio/frontend/backend/openapi.json"

Schema = dict[str, Any]


def _openapi() -> Schema:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def _response_ref(operation: Schema) -> str:
    return operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].rsplit(
        "/",
        1,
    )[1]


def _request_ref(operation: Schema) -> str | None:
    request_body = operation.get("requestBody")
    if request_body is None:
        return None
    return request_body["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]


def test_client_operation_routes_and_models_are_the_studio_openapi_contract() -> None:
    document = _openapi()
    operations = {
        (method, path): (
            operation_id,
            request_model,
            response_model,
        )
        for method, path, operation_id, request_model, response_model in [
            (
                "get",
                "/health",
                "health_health_get",
                None,
                "HealthResponse",
            ),
            (
                "post",
                "/api/v1/evaluation/datasets",
                "create_evaluation_dataset",
                "EvaluationDatasetCreate",
                "EvaluationDatasetRead",
            ),
            (
                "get",
                "/api/v1/evaluation/datasets",
                "list_evaluation_datasets",
                None,
                "EvaluationDatasetList",
            ),
            (
                "get",
                "/api/v1/evaluation/datasets/{dataset_id}",
                "get_evaluation_dataset",
                None,
                "EvaluationDatasetDetail",
            ),
            (
                "post",
                "/api/v1/evaluation/datasets/{dataset_id}/cases",
                "add_evaluation_case",
                "EvaluationCaseCreate",
                "EvaluationCaseRead",
            ),
            (
                "put",
                "/api/v1/evaluation/datasets/{dataset_id}/lock",
                "lock_evaluation_dataset",
                None,
                "EvaluationDatasetRead",
            ),
            (
                "post",
                "/api/v1/evaluation/runs",
                "start_evaluation_run",
                "EvaluationRunStart",
                "EvaluationRunDetail",
            ),
            (
                "get",
                "/api/v1/evaluation/runs",
                "list_evaluation_runs",
                None,
                "EvaluationRunList",
            ),
            (
                "get",
                "/api/v1/evaluation/runs/{run_id}",
                "get_evaluation_run",
                None,
                "EvaluationRunDetail",
            ),
            (
                "get",
                "/api/v1/evaluation/attempts/{attempt_id}",
                "get_evaluation_attempt",
                None,
                "EvaluationAttemptDetail",
            ),
            (
                "put",
                "/api/v1/evaluation/attempts/{attempt_id}/execution",
                "bind_evaluation_attempt_execution",
                "EvaluationExecutionBind",
                "EvaluationAttemptRead",
            ),
            (
                "put",
                "/api/v1/evaluation/attempts/{attempt_id}/result",
                "record_evaluation_attempt_result",
                "EvaluationAttemptResult",
                "EvaluationAttemptRead",
            ),
            (
                "get",
                "/api/v1/evaluation/execution-membership",
                "find_evaluation_execution_membership",
                None,
                "EvaluationExecutionMembershipList",
            ),
            (
                "get",
                "/api/v1/execution-resolution",
                "resolve_execution",
                None,
                "ExecutionResolution",
            ),
            (
                "get",
                "/api/v1/trace-evidence/{trace_id}",
                "get_trace_evidence",
                None,
                "TraceEvidence",
            ),
        ]
    }

    for (method, path), (
        operation_id,
        request_model,
        response_model,
    ) in operations.items():
        operation = document["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert _request_ref(operation) == request_model
        assert _response_ref(operation) == response_model


def test_sdk_request_and_response_fields_match_openapi_components() -> None:
    document = _openapi()
    components = document["components"]["schemas"]
    model_components: dict[type[BaseModel], str] = {
        SemanticExecutionReference: "SemanticExecutionReference",
        DatasetCreate: "EvaluationDatasetCreate",
        DatasetSummary: "EvaluationDatasetSummary",
        DatasetRead: "EvaluationDatasetRead",
        CaseCreate: "EvaluationCaseCreate",
        CaseRead: "EvaluationCaseRead",
        DatasetDetail: "EvaluationDatasetDetail",
        DatasetList: "EvaluationDatasetList",
        RunStart: "EvaluationRunStart",
        RunRead: "EvaluationRunRead",
        AttemptRead: "EvaluationAttemptRead",
        RunCaseRead: "EvaluationRunCase",
        RunDetail: "EvaluationRunDetail",
        AttemptDetail: "EvaluationAttemptDetail",
        AttemptCounts: "EvaluationAttemptCounts",
        RunSummary: "EvaluationRunSummary",
        RunList: "EvaluationRunList",
        AttemptExecutionBind: "EvaluationExecutionBind",
        AttemptResultWrite: "EvaluationAttemptResult",
        ExecutionMembershipItem: "EvaluationExecutionMembership",
        ExecutionMembershipList: "EvaluationExecutionMembershipList",
        ConflictResponse: "EvaluationConflictResponse",
        ExecutionResolutionRead: "ExecutionResolution",
        ExecutionResolutionConflict: "ExecutionResolutionConflictResponse",
        TraceEvidenceRead: "TraceEvidence",
    }

    for sdk_model, component_name in model_components.items():
        sdk_schema = sdk_model.model_json_schema()
        studio_schema = components[component_name]
        assert set(sdk_schema.get("properties", {})) == set(studio_schema.get("properties", {})), component_name
        assert set(sdk_schema.get("required", [])) == set(studio_schema.get("required", [])), component_name
        assert sdk_schema.get("additionalProperties") is False, component_name
        assert studio_schema.get("additionalProperties") is False, component_name

        for property_name in sdk_schema.get("properties", {}):
            sdk_property = sdk_schema["properties"][property_name]
            studio_property = studio_schema["properties"][property_name]
            if component_name == "TraceEvidence" and property_name != "trace_id":
                assert _outer_type(sdk_property, sdk_schema) == _outer_type(
                    studio_property,
                    document,
                ), f"{component_name}.{property_name}"
                continue
            assert _shallow_signature(sdk_property, sdk_schema) == _shallow_signature(
                studio_property,
                document,
            ), f"{component_name}.{property_name}"


def test_agent_is_a_cross_system_evaluation_target_kind() -> None:
    document = _openapi()
    studio_values = set(document["components"]["schemas"]["EvaluationCaseCreate"]["properties"]["target_kind"]["enum"])
    assert studio_values == {member.value for member in TargetKind}
    assert studio_values == {"node", "workflow", "agent"}


def test_health_dto_covers_every_openapi_health_field() -> None:
    document = _openapi()
    studio_schema = document["components"]["schemas"]["HealthResponse"]
    sdk_schema = StudioHealth.model_json_schema()
    assert set(sdk_schema["properties"]) == set(studio_schema["properties"])
    assert set(sdk_schema["required"]) == {"status", "version", "app_name"}


def _shallow_signature(schema: Schema, root: Schema) -> Any:
    if "$ref" in schema:
        reference_name = schema["$ref"].rsplit("/", 1)[1]
        if reference_name == "JsonValue":
            return ("json",)
        target = _resolve_reference(reference_name, root)
        return _shallow_signature(target, root)
    if "anyOf" in schema:
        return (
            "anyOf",
            tuple(
                sorted(
                    (_shallow_signature(item, root) for item in schema["anyOf"]),
                    key=repr,
                )
            ),
        )
    if "oneOf" in schema:
        return ("oneOf", len(schema["oneOf"]))

    schema_type = schema.get("type")
    constraints = tuple(
        (name, schema[name])
        for name in (
            "const",
            "enum",
            "format",
            "maximum",
            "maxItems",
            "maxLength",
            "minimum",
            "minItems",
            "minLength",
            "pattern",
        )
        if name in schema
    )
    if schema_type == "array":
        return (
            "array",
            _shallow_signature(schema["items"], root),
            constraints,
        )
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return ("map", _shallow_signature(additional, root), constraints)
        return ("object", constraints)
    return (schema_type, constraints)


def _resolve_reference(name: str, root: Schema) -> Schema:
    if "$defs" in root and name in root["$defs"]:
        return root["$defs"][name]
    return root["components"]["schemas"][name]


def _outer_type(schema: Schema, root: Schema) -> str:
    if "$ref" in schema:
        reference_name = schema["$ref"].rsplit("/", 1)[1]
        return _outer_type(_resolve_reference(reference_name, root), root)
    return schema.get("type", "union")
