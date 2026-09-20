"""Synthetic OTLP protocol fixtures; live Codex evidence is validated separately."""

import pytest
from opentelemetry import trace

from junjo_coding_agents.codex_telemetry import CodexTelemetry

TRACE = "a" * 32
SAMPLE, TOOL, REQUEST = (f"{i:016x}" for i in (1, 2, 3))


def spans(*items):
    return {"resourceSpans": [{"scopeSpans": [{"spans": list(items)}]}]}


def span(span_id, parent_id, name, start, end, trace_id=TRACE):
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent_id,
        "name": name,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
    }


def log(work, *, receipt=None, request_id=None, success=True, trace_id=TRACE):
    values = {
        "event.name": "codex.tool_result",
        "success": str(success).lower(),
        "output": work.receipt if receipt is None else receipt,
        "arguments": work.id if request_id is None else request_id,
        "conversation.id": "native-child-session",
        "app.version": "0.144.3",
        "model": "source-model",
    }
    return {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "traceId": trace_id,
                                "spanId": TOOL,
                                "attributes": [{"key": k, "value": {"stringValue": v}} for k, v in values.items()],
                            }
                        ]
                    }
                ]
            }
        ]
    }


async def accepted_work(runtime, capture=True):
    execution = runtime.start(capture)
    first = await runtime.review(execution["execution_id"], "correct")
    await runtime.complete(first["request_id"], {"has_bug": False, "explanation": "Correct parity"})
    return runtime.work[first["request_id"]]


def source_tree(work, *, start=None, transport="responses_websocket.stream_request", trace_id=TRACE):
    start = work.issued_ns + 1 if start is None else start
    return [
        span(SAMPLE, "", "run_sampling_request", start, start + 100, trace_id),
        span(TOOL, SAMPLE, "exec", start + 50, start + 90, trace_id),
        span(REQUEST, SAMPLE, transport, start + 2, start + 80, trace_id),
    ]


async def test_out_of_order_batches_preserve_node_parent_source_link_and_real_times(runtime, exporter):
    work = await accepted_work(runtime)
    adapter = CodexTelemetry(runtime)
    sample, tool, request = source_tree(work)
    adapter.receive_logs(log(work))
    adapter.receive_traces(spans(tool, request))
    assert not work.model_span_ids
    adapter.receive_traces(spans(sample))
    adapter.receive_traces(spans(sample, tool, request))
    adapter.receive_logs(log(work))
    models = [s for s in exporter.get_finished_spans() if s.name == "Codex model request"]
    assert len(models) == 1
    model = models[0]
    parent = trace.get_current_span(work.context).get_span_context()
    assert model.parent.span_id == parent.span_id
    assert model.context.trace_id == parent.trace_id
    assert model.start_time == int(request["startTimeUnixNano"])
    assert model.end_time == int(request["endTimeUnixNano"])
    assert model.links[0].context.trace_id == int(TRACE, 16)
    assert model.links[0].context.span_id == int(REQUEST, 16)
    assert model.attributes["gen_ai.request.model"] == "source-model"
    assert model.attributes["coding_agent.session.id"] == "native-child-session"
    assert "junjo.span_type" not in model.attributes
    assert "gen_ai.usage.input_tokens" not in model.attributes


@pytest.mark.parametrize(
    "bad_log",
    [
        {"receipt": "unaccepted-result"},
        {"request_id": "other-work"},
        {"success": False},
        {"trace_id": "b" * 32},
    ],
)
async def test_no_attribution_without_matching_accepted_source_evidence(runtime, bad_log):
    work = await accepted_work(runtime)
    adapter = CodexTelemetry(runtime)
    adapter.receive_traces(spans(*source_tree(work)))
    adapter.receive_logs(log(work, **bad_log))
    assert not work.model_span_ids


@pytest.mark.parametrize(
    "source_kwargs",
    [
        {"start": 1},
        {"transport": "unknown_future_transport"},
    ],
)
async def test_pre_handoff_or_unknown_request_is_not_fabricated(runtime, source_kwargs):
    work = await accepted_work(runtime)
    adapter = CodexTelemetry(runtime)
    adapter.receive_traces(spans(*source_tree(work, **source_kwargs)))
    adapter.receive_logs(log(work))
    assert not work.model_span_ids


async def test_disabled_execution_ignored_even_while_another_capture_is_active(runtime, exporter):
    runtime.start(True)
    work = await accepted_work(runtime, False)
    adapter = CodexTelemetry(runtime)
    adapter.receive_traces(spans(*source_tree(work)))
    adapter.receive_logs(log(work))
    assert not work.model_span_ids
    assert not adapter.completions
    assert not exporter.get_finished_spans()
