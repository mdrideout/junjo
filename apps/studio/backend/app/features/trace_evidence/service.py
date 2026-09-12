"""Application service for cohesive trace evidence."""

from __future__ import annotations

from urllib.parse import quote

from app.features.evaluation import service as evaluation_service
from app.features.evaluation.schemas import OpenTelemetrySpanReference
from app.features.execution_resolution import service as resolution_service
from app.features.trace_evidence import repository
from app.features.trace_evidence.assembler import (
    assemble_attempt_evidence_manifest,
    assemble_trace_evidence,
    select_attempt_span_evidence,
)
from app.features.trace_evidence.schemas import (
    AttemptEvidenceManifest,
    AttemptEvidenceSubject,
    SelectedSpanEvidenceResponse,
    TraceEvidence,
)


async def get_trace_evidence(trace_id: str) -> TraceEvidence | None:
    """Return one normalized trace enriched with verified annotations."""
    spans = await repository.get_trace(trace_id)
    if not spans:
        return None
    return assemble_trace_evidence(trace_id, spans)


async def _get_attempt_trace_evidence(
    attempt_id: str,
) -> tuple[AttemptEvidenceSubject, TraceEvidence] | None:
    attempt_detail = await evaluation_service.get_attempt(attempt_id)
    reference = attempt_detail.attempt.subject_evidence
    if reference is None:
        return None

    if isinstance(reference, OpenTelemetrySpanReference):
        trace_id = reference.trace_id
        span_id = reference.span_id
        encoded_service_name = quote(reference.service_name, safe="")
        trace_path = f"/traces/{encoded_service_name}/{trace_id}/{span_id}"
        subject = AttemptEvidenceSubject(
            attempt_id=attempt_id,
            reference=reference,
            trace_id=trace_id,
            span_id=span_id,
            detail_path=trace_path,
            failure_path=trace_path,
            trace_path=trace_path,
        )
    else:
        resolution = await resolution_service.resolve_execution(
            service_namespace=reference.service_namespace,
            service_name=reference.service_name,
            executable_type=reference.executable_type,
            runtime_id=reference.runtime_id,
        )
        if resolution is None:
            return None
        trace_id = resolution.trace_id
        span_id = resolution.span_id
        subject = AttemptEvidenceSubject(
            attempt_id=attempt_id,
            reference=reference,
            trace_id=trace_id,
            span_id=span_id,
            detail_path=resolution.detail_path,
            failure_path=resolution.failure_path,
            trace_path=resolution.trace_path,
        )

    evidence = await get_trace_evidence(trace_id)
    if evidence is None:
        return None
    subject_span = next((span for span in evidence.spans if span.span_id == span_id), None)
    if subject_span is None:
        return None
    resource = subject_span.resource_attributes_json
    if (
        resource.get("service.name") != reference.service_name
        or resource.get("service.namespace", "") != reference.service_namespace
    ):
        return None
    return subject, evidence


async def get_attempt_evidence_manifest(attempt_id: str) -> AttemptEvidenceManifest | None:
    """Return a payload-light manifest for one Attempt's exact bound trace."""
    resolved = await _get_attempt_trace_evidence(attempt_id)
    if resolved is None:
        return None
    subject, evidence = resolved
    return assemble_attempt_evidence_manifest(subject=subject, evidence=evidence)


async def get_attempt_span_evidence(
    *,
    attempt_id: str,
    span_ids: list[str],
) -> SelectedSpanEvidenceResponse | None:
    """Return complete evidence only for the requested bound-trace spans."""
    resolved = await _get_attempt_trace_evidence(attempt_id)
    if resolved is None:
        return None
    subject, evidence = resolved
    return select_attempt_span_evidence(
        subject=subject,
        evidence=evidence,
        span_ids=span_ids,
    )
