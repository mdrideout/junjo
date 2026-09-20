"""Translate attributable Codex OTLP evidence, never assistant-reported timings.

Codex 0.144.3 emits a source span tree and tool-result logs carrying the source
span identity. A completion receipt joins an accepted Junjo work request to the
tool result; source ancestry locates the sampling request that generated it.
Only that sampling request's model transport spans are projected. Source IDs
remain available as OTel links; the source tree is not rewritten in place.
"""

from dataclasses import dataclass
from typing import Any

from opentelemetry.trace import Link, SpanContext, SpanKind, Status, StatusCode, TraceFlags

from .runtime import Runtime, Work


def attributes(item: dict[str, Any]) -> dict[str, Any]:
    return {a["key"]: next(iter(a["value"].values())) for a in item.get("attributes", []) if a.get("value")}


@dataclass(frozen=True)
class SourceSpan:
    trace_id: str
    span_id: str
    parent_id: str
    name: str
    start: int
    end: int
    model: str | None
    error: bool


@dataclass(frozen=True)
class Completion:
    work_id: str
    trace_id: str
    span_id: str
    session_id: str
    version: str
    model: str


class CodexTelemetry:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.spans: dict[tuple[str, str], SourceSpan] = {}
        self.completions: set[Completion] = set()
        self.exported: set[tuple[str, str]] = set()

    def receive_traces(self, payload: dict[str, Any]) -> None:
        if not any(e.capture for e in self.runtime.executions.values()):
            return
        for resource in payload.get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for item in scope.get("spans", []):
                    a = attributes(item)
                    span = SourceSpan(
                        item["traceId"],
                        item["spanId"],
                        item.get("parentSpanId", ""),
                        item["name"],
                        int(item["startTimeUnixNano"]),
                        int(item["endTimeUnixNano"]),
                        a.get("model"),
                        item.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR"),
                    )
                    self.spans[(span.trace_id, span.span_id)] = span
        self.reconcile()

    def receive_logs(self, payload: dict[str, Any]) -> None:
        # Unrelated payload text and user/account attributes are not retained.
        for resource in payload.get("resourceLogs", []):
            for scope in resource.get("scopeLogs", []):
                for item in scope.get("logRecords", []):
                    a = attributes(item)
                    if a.get("event.name") != "codex.tool_result" or a.get("success") not in (True, "true"):
                        continue
                    for work in self.runtime.work.values():
                        if (
                            not work.run.execution.capture
                            or not work.receipt
                            or work.receipt not in str(a.get("output", ""))
                            or work.id not in str(a.get("arguments", ""))
                        ):
                            continue
                        if not item.get("traceId") or not item.get("spanId"):
                            continue
                        self.completions.add(
                            Completion(
                                work.id,
                                item["traceId"],
                                item["spanId"],
                                str(a.get("conversation.id", "")),
                                str(a.get("app.version", "")),
                                str(a.get("model", "")),
                            )
                        )
        self.reconcile()

    def ancestor(self, key: tuple[str, str], name: str) -> SourceSpan | None:
        visited = set()
        while key in self.spans and key not in visited:
            visited.add(key)
            span = self.spans[key]
            if span.name == name:
                return span
            key = (span.trace_id, span.parent_id)
        return None

    def reconcile(self) -> None:
        for completion in self.completions:
            sample = self.ancestor((completion.trace_id, completion.span_id), "run_sampling_request")
            if sample is None:
                continue  # Parent span batches may arrive after their children.
            work = self.runtime.work[completion.work_id]
            if sample.start < work.issued_ns:
                continue  # Never assign a request that preceded this work handoff.
            for key, source in self.spans.items():
                if key in self.exported or source.trace_id != sample.trace_id:
                    continue
                # These are concrete transport operations observed in Codex,
                # not timing wrappers around a whole reasoning/tool loop.
                if source.name != "responses_websocket.stream_request":
                    continue
                if self.ancestor(key, "run_sampling_request") != sample:
                    continue
                self.emit_model(work, source, completion)
                self.exported.add(key)

    def emit_model(self, work: Work, source: SourceSpan, completion: Completion) -> None:
        source_context = SpanContext(
            trace_id=int(source.trace_id, 16),
            span_id=int(source.span_id, 16),
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        span = self.runtime.tracer.start_span(
            "Codex model request",
            context=work.context,
            kind=SpanKind.CLIENT,
            start_time=source.start,
            links=[Link(source_context)],
            attributes={
                "gen_ai.operation.name": "responses",
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": completion.model,
                "coding_agent.request.id": work.id,
                "coding_agent.run.id": work.run.id,
                "coding_agent.session.id": completion.session_id,
                "coding_agent.host.version": completion.version,
                "coding_agent.source.trace_id": source.trace_id,
                "coding_agent.source.span_id": source.span_id,
                "coding_agent.source.operation": source.name,
                "coding_agent.attribution": "completion-receipt-and-source-ancestry",
            },
        )
        if source.error:
            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=source.end)
        work.model_span_ids.add(format(span.get_span_context().span_id, "016x"))
