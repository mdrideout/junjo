"""Tests for the DataFusion-based Parquet query engine.

These tests validate that the backend can query Parquet span data using
DataFusion without relying on any legacy metadata indexing layer.
"""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.features.agent_diagnostics.assembler import assemble_agent_detail
from app.features.otel_spans.datafusion_query import UnifiedSpanQuery
from tests.helpers.junjo_fixture_loader import (
    list_junjo_fixture_case_names,
    list_valid_transport_fixture_ids,
    load_junjo_fixture_case,
    load_valid_transport_fixture,
)
from tests.helpers.junjo_transport_builders import (
    SPAN_SCHEMA,
    agent_spans_for_case,
    api_span_to_parquet_row,
    normalize_api_spans,
    workflow_spans_for_case,
)

JUNJO_FIXTURE_CASE_NAMES = list_junjo_fixture_case_names()
AGENT_FIXTURE_IDS = [
    fixture_id
    for fixture_id in list_valid_transport_fixture_ids()
    if fixture_id.startswith("agent/")
]


def _ns_now() -> int:
    return int(datetime.now(UTC).timestamp() * 1e9)


def create_test_span(
    *,
    trace_id: str,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    service_name: str = "test-service",
    name: str = "test-span",
    span_kind: int = 1,
    start_ns: int | None = None,
    duration_ns: int = 100_000,
    status_code: int = 0,
    attributes: dict | None = None,
    events: list[dict] | None = None,
) -> dict:
    if span_id is None:
        span_id = uuid.uuid4().hex[:16]
    if start_ns is None:
        start_ns = _ns_now()

    end_ns = start_ns + duration_ns

    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "name": name,
        "span_kind": span_kind,
        "start_time": pa.scalar(start_ns, type=pa.timestamp("ns", tz="UTC")),
        "end_time": pa.scalar(end_ns, type=pa.timestamp("ns", tz="UTC")),
        "duration_ns": duration_ns,
        "status_code": status_code,
        "status_message": None,
        "attributes": json.dumps(attributes or {}),
        "events": json.dumps(events or []),
        "links": "[]",
        "trace_flags": 0,
        "trace_state": None,
        "dropped_attributes_count": 0,
        "dropped_events_count": 0,
        "dropped_links_count": 0,
        "resource_attributes": json.dumps({"service.name": service_name}),
        "resource_dropped_attributes_count": 0,
    }


def write_spans_to_parquet(spans: list[dict], file_path: str) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)
    pq.write_table(table, file_path)


@pytest.fixture
def temp_parquet_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def simple_parquet_file(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    now_ns = _ns_now()

    spans = [
        create_test_span(
            trace_id=trace_id,
            span_id="span1111111111",
            name="root-span",
            start_ns=now_ns,
        ),
        create_test_span(
            trace_id=trace_id,
            span_id="span2222222222",
            parent_span_id="span1111111111",
            name="child-span-1",
            start_ns=now_ns + 1_000,
        ),
        create_test_span(
            trace_id=trace_id,
            span_id="span3333333333",
            parent_span_id="span1111111111",
            name="child-span-2",
            start_ns=now_ns + 2_000,
        ),
    ]

    file_path = os.path.join(temp_parquet_dir, "test.parquet")
    write_spans_to_parquet(spans, file_path)

    return {"file_path": file_path, "trace_id": trace_id}


def test_query_spans_by_trace_id(simple_parquet_file):
    query = UnifiedSpanQuery()
    query.register_cold([simple_parquet_file["file_path"]])

    results = query.query_spans_two_tier(trace_id=simple_parquet_file["trace_id"])
    assert len(results) == 3
    assert {r["span_id"] for r in results} == {
        "span1111111111",
        "span2222222222",
        "span3333333333",
    }


def test_query_root_only(simple_parquet_file):
    query = UnifiedSpanQuery()
    query.register_cold([simple_parquet_file["file_path"]])

    results = query.query_spans_two_tier(
        trace_id=simple_parquet_file["trace_id"],
        root_only=True,
    )
    assert len(results) == 1
    assert results[0]["name"] == "root-span"
    assert results[0]["parent_span_id"] is None or results[0]["parent_span_id"] == ""


def test_query_distinct_service_names_from_parquet(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    file_path = os.path.join(temp_parquet_dir, "svc.parquet")
    write_spans_to_parquet(
        [
            create_test_span(trace_id=trace_id, service_name="alpha"),
            create_test_span(trace_id=trace_id, service_name="beta"),
            create_test_span(trace_id=trace_id, service_name="alpha"),
        ],
        file_path,
    )

    query = UnifiedSpanQuery()
    query.register_cold([file_path])
    assert query.query_distinct_service_names() == ["alpha", "beta"]


def test_dedup_prefers_cold_over_hot(temp_parquet_dir):
    trace_id = uuid.uuid4().hex

    cold_path = os.path.join(temp_parquet_dir, "cold.parquet")
    hot_path = os.path.join(temp_parquet_dir, "hot.parquet")

    # Same span_id in both tiers; cold should win.
    write_spans_to_parquet(
        [
            create_test_span(
                trace_id=trace_id,
                span_id="dup-span",
                service_name="svc",
                name="cold-name",
            )
        ],
        cold_path,
    )
    write_spans_to_parquet(
        [
            create_test_span(
                trace_id=trace_id,
                span_id="dup-span",
                service_name="svc",
                name="hot-name",
            )
        ],
        hot_path,
    )

    query = UnifiedSpanQuery()
    query.register_cold([cold_path])
    query.register_hot(hot_path)
    results = query.query_spans_two_tier(trace_id=trace_id)

    assert len(results) == 1
    assert results[0]["span_id"] == "dup-span"
    assert results[0]["name"] == "cold-name"


def test_dedup_does_not_collapse_across_traces(temp_parquet_dir):
    """Dedup must not collapse spans from different traces.

    span_id is only unique within a trace, so dedup must use (trace_id, span_id).
    """
    cold_trace_id = uuid.uuid4().hex
    hot_trace_id = uuid.uuid4().hex

    cold_path = os.path.join(temp_parquet_dir, "cold_multi_trace.parquet")
    hot_path = os.path.join(temp_parquet_dir, "hot_multi_trace.parquet")

    shared_span_id = "dup-span"

    write_spans_to_parquet(
        [
            create_test_span(
                trace_id=cold_trace_id,
                span_id=shared_span_id,
                service_name="svc",
                name="cold-trace-span",
            )
        ],
        cold_path,
    )
    write_spans_to_parquet(
        [
            create_test_span(
                trace_id=hot_trace_id,
                span_id=shared_span_id,
                service_name="svc",
                name="hot-trace-span",
            )
        ],
        hot_path,
    )

    query = UnifiedSpanQuery()
    query.register_cold([cold_path])
    query.register_hot(hot_path)
    results = query.query_spans_two_tier(service_name="svc", order_by="start_time ASC")

    assert len(results) == 2
    assert {(r["trace_id"], r["span_id"], r["name"]) for r in results} == {
        (cold_trace_id, shared_span_id, "cold-trace-span"),
        (hot_trace_id, shared_span_id, "hot-trace-span"),
    }


def test_register_cold_multiple_files(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    file_a = os.path.join(temp_parquet_dir, "a.parquet")
    file_b = os.path.join(temp_parquet_dir, "b.parquet")

    write_spans_to_parquet([create_test_span(trace_id=trace_id, name="a")], file_a)
    write_spans_to_parquet([create_test_span(trace_id=trace_id, name="b")], file_b)

    query = UnifiedSpanQuery()
    query.register_cold([file_a, file_b])
    results = query.query_spans_two_tier(trace_id=trace_id, order_by="start_time ASC")
    assert {r["name"] for r in results} == {"a", "b"}


def test_parses_attributes_and_events_json(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    file_path = os.path.join(temp_parquet_dir, "json.parquet")

    write_spans_to_parquet(
        [
            create_test_span(
                trace_id=trace_id,
                service_name="svc",
                attributes={"junjo.span_type": "workflow", "other": "value"},
                events=[{"name": "set_state", "timeUnixNano": "123", "attributes": {"a": 1}}],
            )
        ],
        file_path,
    )

    query = UnifiedSpanQuery()
    query.register_cold([file_path])
    results = query.query_spans_two_tier(trace_id=trace_id)
    assert results[0]["attributes_json"]["junjo.span_type"] == "workflow"
    assert results[0]["attributes_json"]["other"] == "value"
    assert results[0]["events_json"][0]["name"] == "set_state"
    assert results[0]["events_json"][0]["timeUnixNano"] == "123"


def test_query_exact_executable_identity_filters_before_and_after_datafusion(
    temp_parquet_dir,
):
    trace_id = uuid.uuid4().hex
    file_path = os.path.join(temp_parquet_dir, "execution-resolution.parquet")
    expected = create_test_span(
        trace_id=trace_id,
        span_id="a" * 16,
        service_name="ai-chat",
        attributes={
            "junjo.telemetry.contract_version": 2,
            "junjo.span_type": "workflow",
            "junjo.executable_runtime_id": "run_100%",
        },
    )
    write_spans_to_parquet(
        [
            expected,
            create_test_span(
                trace_id=trace_id,
                span_id="b" * 16,
                service_name="ai-chat",
                attributes={
                    "junjo.telemetry.contract_version": 2,
                    "junjo.span_type": "agent",
                    "junjo.executable_runtime_id": "run_100%",
                },
            ),
            create_test_span(
                trace_id=trace_id,
                span_id="c" * 16,
                service_name="ai-chat",
                attributes={
                    "junjo.telemetry.contract_version": 2,
                    "junjo.span_type": "workflow",
                    "junjo.executable_runtime_id": "run_1000",
                },
            ),
        ],
        file_path,
    )

    query = UnifiedSpanQuery()
    query.register_cold([file_path])
    results = query.query_spans_two_tier(
        service_name="ai-chat",
        executable_type="workflow",
        executable_runtime_id="run_100%",
    )

    assert [row["span_id"] for row in results] == ["a" * 16]


def test_register_cold_skips_empty_parquet_files(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    valid_path = os.path.join(temp_parquet_dir, "valid.parquet")
    empty_path = os.path.join(temp_parquet_dir, "empty.parquet")

    write_spans_to_parquet([create_test_span(trace_id=trace_id, name="valid")], valid_path)
    with open(empty_path, "wb") as f:
        f.write(b"")

    query = UnifiedSpanQuery()
    query.register_cold([empty_path, valid_path])
    results = query.query_spans_two_tier(trace_id=trace_id)

    assert len(results) == 1
    assert results[0]["name"] == "valid"


def test_register_cold_with_only_empty_files_returns_no_results(temp_parquet_dir):
    trace_id = uuid.uuid4().hex
    empty_path = os.path.join(temp_parquet_dir, "empty_only.parquet")
    with open(empty_path, "wb") as f:
        f.write(b"")

    query = UnifiedSpanQuery()
    query.register_cold([empty_path])
    assert query.query_spans_two_tier(trace_id=trace_id) == []


@pytest.mark.parametrize("case_name", JUNJO_FIXTURE_CASE_NAMES)
def test_current_junjo_fixture_round_trips_from_cold_parquet(temp_parquet_dir, case_name):
    case = load_junjo_fixture_case(case_name)
    file_path = os.path.join(temp_parquet_dir, f"{case_name}.parquet")
    write_spans_to_parquet([api_span_to_parquet_row(span) for span in case["spans"]], file_path)

    query = UnifiedSpanQuery()
    query.register_cold([file_path])

    results = query.query_spans_two_tier(trace_id=case["trace_id"], order_by="start_time ASC")
    assert normalize_api_spans(results) == normalize_api_spans(case["spans"])


@pytest.mark.parametrize("case_name", JUNJO_FIXTURE_CASE_NAMES)
def test_current_junjo_fixture_round_trips_from_hot_parquet(temp_parquet_dir, case_name):
    case = load_junjo_fixture_case(case_name)
    file_path = os.path.join(temp_parquet_dir, f"{case_name}.hot.parquet")
    write_spans_to_parquet([api_span_to_parquet_row(span) for span in case["spans"]], file_path)

    query = UnifiedSpanQuery()
    query.register_hot(file_path)

    results = query.query_spans_two_tier(trace_id=case["trace_id"], order_by="start_time ASC")
    assert normalize_api_spans(results) == normalize_api_spans(case["spans"])


@pytest.mark.parametrize("case_name", JUNJO_FIXTURE_CASE_NAMES)
def test_current_junjo_fixture_round_trips_from_fused_hot_and_cold(
    temp_parquet_dir,
    case_name,
):
    case = load_junjo_fixture_case(case_name)
    cold_path = os.path.join(temp_parquet_dir, f"{case_name}.cold.parquet")
    hot_path = os.path.join(temp_parquet_dir, f"{case_name}.hot.parquet")
    rows = [api_span_to_parquet_row(span) for span in case["spans"]]
    write_spans_to_parquet(rows, cold_path)
    write_spans_to_parquet(rows, hot_path)

    query = UnifiedSpanQuery()
    query.register_cold([cold_path])
    query.register_hot(hot_path)

    results = query.query_spans_two_tier(trace_id=case["trace_id"], order_by="start_time ASC")
    assert normalize_api_spans(results) == normalize_api_spans(case["spans"])


@pytest.mark.parametrize("case_name", JUNJO_FIXTURE_CASE_NAMES)
def test_workflow_only_query_finds_current_junjo_workflow_spans(temp_parquet_dir, case_name):
    case = load_junjo_fixture_case(case_name)
    file_path = os.path.join(temp_parquet_dir, f"{case_name}.workflow.parquet")
    write_spans_to_parquet([api_span_to_parquet_row(span) for span in case["spans"]], file_path)

    query = UnifiedSpanQuery()
    query.register_cold([file_path])

    results = query.query_spans_two_tier(
        service_name=case["service_name"],
        workflow_only=True,
        order_by="start_time ASC",
    )
    assert normalize_api_spans(results) == normalize_api_spans(workflow_spans_for_case(case))


@pytest.mark.parametrize("fixture_id", AGENT_FIXTURE_IDS)
def test_agent_fixture_round_trips_and_assembles_from_parquet(temp_parquet_dir, fixture_id):
    case = load_valid_transport_fixture(fixture_id)
    file_path = os.path.join(temp_parquet_dir, f"{fixture_id.replace('/', '_')}.parquet")
    write_spans_to_parquet([api_span_to_parquet_row(span) for span in case["spans"]], file_path)

    query = UnifiedSpanQuery()
    query.register_cold([file_path])
    trace_results = query.query_spans_two_tier(
        trace_id=case["trace_id"],
        order_by="start_time ASC",
    )
    agent_results = query.query_spans_two_tier(
        service_name=case["service_name"],
        agent_only=True,
        order_by="start_time ASC",
    )
    assert normalize_api_spans(trace_results) == normalize_api_spans(case["spans"])
    assert normalize_api_spans(agent_results) == normalize_api_spans(agent_spans_for_case(case))

    expected = [
        assemble_agent_detail(owner, case["spans"]).model_dump(mode="json")
        for owner in sorted(agent_spans_for_case(case), key=lambda span: span["span_id"])
    ]
    observed = [
        assemble_agent_detail(owner, trace_results).model_dump(mode="json")
        for owner in sorted(agent_results, key=lambda span: span["span_id"])
    ]
    assert observed == expected
