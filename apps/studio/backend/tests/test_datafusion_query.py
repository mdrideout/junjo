"""Tests for DataFusion query module.

Tests the DataFusion-based Parquet querying functionality.
Uses pyarrow to create real Parquet files matching the Go ingestion schema.
"""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.db_duckdb import datafusion_query

# ============================================================================
# Test Fixtures
# ============================================================================


# Arrow schema matching Go ingestion (parquet_writer.go)
SPAN_SCHEMA = pa.schema(
    [
        pa.field("span_id", pa.string(), nullable=False),
        pa.field("trace_id", pa.string(), nullable=False),
        pa.field("parent_span_id", pa.string(), nullable=True),
        pa.field("service_name", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("span_kind", pa.int8(), nullable=False),
        pa.field("start_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("end_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("duration_ns", pa.int64(), nullable=False),
        pa.field("status_code", pa.int8(), nullable=False),
        pa.field("status_message", pa.string(), nullable=True),
        pa.field("attributes", pa.string(), nullable=False),
        pa.field("events", pa.string(), nullable=False),
        pa.field("resource_attributes", pa.string(), nullable=False),
    ]
)


def create_test_span(
    trace_id: str,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    service_name: str = "test-service",
    name: str = "test-span",
    span_kind: int = 1,
    start_ns: int | None = None,
    duration_ns: int = 100000,
    status_code: int = 0,
    attributes: dict | None = None,
) -> dict:
    """Create a test span dictionary."""
    if span_id is None:
        span_id = uuid.uuid4().hex[:16]
    if start_ns is None:
        start_ns = int(datetime.now(UTC).timestamp() * 1e9)
    end_ns = start_ns + duration_ns

    attrs = attributes or {}

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
        "attributes": json.dumps(attrs),
        "events": "[]",
        "resource_attributes": json.dumps({"service.name": service_name}),
    }


def write_spans_to_parquet(spans: list[dict], file_path: str) -> None:
    """Write spans to a Parquet file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)
    pq.write_table(table, file_path)


@pytest.fixture
def temp_parquet_dir():
    """Create a temporary directory for Parquet files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def simple_parquet_file(temp_parquet_dir):
    """Create a simple Parquet file with 3 spans."""
    trace_id = uuid.uuid4().hex
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)

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
            start_ns=now_ns + 1000,
        ),
        create_test_span(
            trace_id=trace_id,
            span_id="span3333333333",
            parent_span_id="span1111111111",
            name="child-span-2",
            start_ns=now_ns + 2000,
        ),
    ]

    file_path = os.path.join(temp_parquet_dir, "test.parquet")
    write_spans_to_parquet(spans, file_path)

    return {"file_path": file_path, "trace_id": trace_id, "spans": spans}


# ============================================================================
# Unit Tests
# ============================================================================


class TestGetContext:
    """Tests for get_context function."""

    def test_returns_session_context(self):
        """Should return a DataFusion SessionContext."""
        import datafusion

        ctx = datafusion_query.get_context()
        assert isinstance(ctx, datafusion.SessionContext)

    def test_returns_singleton(self):
        """Should return same context on multiple calls."""
        ctx1 = datafusion_query.get_context()
        ctx2 = datafusion_query.get_context()
        assert ctx1 is ctx2


class TestQuerySpansFromParquet:
    """Tests for query_spans_from_parquet function."""

    def test_empty_file_paths(self):
        """Should return empty list for empty file paths."""
        result = datafusion_query.query_spans_from_parquet([])
        assert result == []

    def test_query_all_spans(self, simple_parquet_file):
        """Should return all spans from file."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]]
        )
        assert len(result) == 3

    def test_query_with_filter(self, simple_parquet_file):
        """Should filter spans by SQL predicate."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]],
            filter_sql="name = 'root-span'",
        )
        assert len(result) == 1
        assert result[0]["name"] == "root-span"

    def test_query_with_limit(self, simple_parquet_file):
        """Should limit number of results."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]],
            limit=2,
        )
        assert len(result) == 2

    def test_query_with_order_by(self, simple_parquet_file):
        """Should order results."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]],
            order_by="name ASC",
        )
        assert len(result) == 3
        assert result[0]["name"] == "child-span-1"
        assert result[1]["name"] == "child-span-2"
        assert result[2]["name"] == "root-span"


class TestSpanConversion:
    """Tests for span data conversion to API format."""

    def test_converts_span_fields(self, simple_parquet_file):
        """Should convert all span fields correctly."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]],
            filter_sql="name = 'root-span'",
        )
        span = result[0]

        # Check required fields exist
        assert "span_id" in span
        assert "trace_id" in span
        assert "parent_span_id" in span
        assert "service_name" in span
        assert "name" in span
        assert "kind" in span  # Mapped from span_kind
        assert "start_time" in span
        assert "end_time" in span
        assert "status_code" in span
        assert "attributes_json" in span
        assert "events_json" in span

    def test_converts_span_kind_to_string(self, simple_parquet_file):
        """Should convert span_kind int to string name."""
        result = datafusion_query.query_spans_from_parquet(
            [simple_parquet_file["file_path"]],
            limit=1,
        )
        # span_kind=1 should be SERVER
        assert result[0]["kind"] == "SERVER"

    def test_parses_attributes_json(self, temp_parquet_dir):
        """Should parse attributes JSON string to dict."""
        trace_id = uuid.uuid4().hex
        spans = [
            create_test_span(
                trace_id=trace_id,
                attributes={"key": "value", "count": 42},
            )
        ]
        file_path = os.path.join(temp_parquet_dir, "attrs.parquet")
        write_spans_to_parquet(spans, file_path)

        result = datafusion_query.query_spans_from_parquet([file_path])
        assert result[0]["attributes_json"] == {"key": "value", "count": 42}

    def test_extracts_junjo_fields(self, temp_parquet_dir):
        """Should extract junjo_* fields from attributes."""
        trace_id = uuid.uuid4().hex
        spans = [
            create_test_span(
                trace_id=trace_id,
                attributes={
                    "junjo.span_type": "workflow",
                    "junjo.id": "wf-123",
                    "junjo.parent_id": "wf-parent",
                    "other_attr": "value",
                },
            )
        ]
        file_path = os.path.join(temp_parquet_dir, "junjo.parquet")
        write_spans_to_parquet(spans, file_path)

        result = datafusion_query.query_spans_from_parquet([file_path])
        span = result[0]

        assert span["junjo_span_type"] == "workflow"
        assert span["junjo_id"] == "wf-123"
        assert span["junjo_parent_id"] == "wf-parent"
        # Junjo fields should be removed from attributes_json
        assert "junjo.span_type" not in span["attributes_json"]
        assert "other_attr" in span["attributes_json"]


class TestGetSpansByTraceId:
    """Tests for get_spans_by_trace_id function."""

    def test_returns_spans_for_trace(self, simple_parquet_file):
        """Should return all spans for a trace."""
        result = datafusion_query.get_spans_by_trace_id(
            simple_parquet_file["trace_id"],
            [simple_parquet_file["file_path"]],
        )
        assert len(result) == 3
        for span in result:
            assert span["trace_id"] == simple_parquet_file["trace_id"]

    def test_returns_empty_for_nonexistent_trace(self, simple_parquet_file):
        """Should return empty list for non-existent trace."""
        result = datafusion_query.get_spans_by_trace_id(
            "nonexistent_trace_id_here_",
            [simple_parquet_file["file_path"]],
        )
        assert result == []


class TestGetSpanById:
    """Tests for get_span_by_id function."""

    def test_returns_specific_span(self, simple_parquet_file):
        """Should return specific span by ID."""
        result = datafusion_query.get_span_by_id(
            "span1111111111",
            simple_parquet_file["trace_id"],
            [simple_parquet_file["file_path"]],
        )
        assert result is not None
        assert result["span_id"] == "span1111111111"

    def test_returns_none_for_nonexistent_span(self, simple_parquet_file):
        """Should return None for non-existent span."""
        result = datafusion_query.get_span_by_id(
            "nonexistent____",
            simple_parquet_file["trace_id"],
            [simple_parquet_file["file_path"]],
        )
        assert result is None


class TestGetRootSpans:
    """Tests for get_root_spans function."""

    def test_returns_root_spans_only(self, simple_parquet_file):
        """Should return only spans without parent."""
        result = datafusion_query.get_root_spans(
            "test-service",
            [simple_parquet_file["file_path"]],
        )
        assert len(result) == 1
        assert result[0]["name"] == "root-span"
        assert result[0]["parent_span_id"] is None or result[0]["parent_span_id"] == ""


class TestGetServiceSpans:
    """Tests for get_service_spans function."""

    def test_returns_spans_for_service(self, simple_parquet_file):
        """Should return all spans for a service."""
        result = datafusion_query.get_service_spans(
            "test-service",
            [simple_parquet_file["file_path"]],
        )
        assert len(result) == 3

    def test_respects_limit(self, simple_parquet_file):
        """Should respect limit parameter."""
        result = datafusion_query.get_service_spans(
            "test-service",
            [simple_parquet_file["file_path"]],
            limit=2,
        )
        assert len(result) == 2


class TestGetWorkflowSpans:
    """Tests for get_workflow_spans function."""

    def test_returns_workflow_spans_only(self, temp_parquet_dir):
        """Should return only workflow type spans."""
        trace_id = uuid.uuid4().hex
        spans = [
            create_test_span(
                trace_id=trace_id,
                name="workflow-span",
                attributes={"junjo.span_type": "workflow"},
            ),
            create_test_span(
                trace_id=trace_id,
                name="node-span",
                attributes={"junjo.span_type": "node"},
            ),
            create_test_span(
                trace_id=trace_id,
                name="regular-span",
            ),
        ]
        file_path = os.path.join(temp_parquet_dir, "workflow.parquet")
        write_spans_to_parquet(spans, file_path)

        result = datafusion_query.get_workflow_spans(
            "test-service",
            [file_path],
        )

        assert len(result) == 1
        assert result[0]["name"] == "workflow-span"
        assert result[0]["junjo_span_type"] == "workflow"
