"""Application service for cohesive trace evidence."""

from __future__ import annotations

from app.features.trace_evidence import repository
from app.features.trace_evidence.assembler import assemble_trace_evidence
from app.features.trace_evidence.schemas import TraceEvidence


async def get_trace_evidence(trace_id: str) -> TraceEvidence | None:
    """Return one normalized trace enriched with verified annotations."""
    spans = await repository.get_trace(trace_id)
    if not spans:
        return None
    return assemble_trace_evidence(trace_id, spans)
