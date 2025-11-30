"""V4 Full Stack Integration Tests.

Tests the complete V4 query flow:
1. Create Parquet files (simulating Go ingestion)
2. Index into DuckDB (parquet_files, span_metadata, services)
3. Query via repository → DataFusion → Parquet

Tests verify:
- List of service names
- List of root spans / traces
- Fetched span data (child spans)
- Workflow span filtering

Note: These tests mock the WAL client to isolate Parquet-only queries.
For full WAL fusion tests, see test_v4_wal_fusion_integration.py.
"""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.db_duckdb import v4_repository
from app.features.otel_spans import repository as otel_repository
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata


# Mock WAL queries to return empty results (isolates Parquet-only testing)
@pytest.fixture(autouse=True)
def mock_wal_queries():
    """Mock WAL query functions to return empty results.

    This isolates the V4 Parquet-only flow from WAL fusion.
    """
    with patch.object(otel_repository, "_get_wal_distinct_service_names", new_callable=AsyncMock) as mock_services, \
         patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock_trace, \
         patch.object(otel_repository, "_get_wal_root_spans", new_callable=AsyncMock) as mock_root:
        mock_services.return_value = []
        mock_trace.return_value = []
        mock_root.return_value = []
        yield {
            "service_names": mock_services,
            "trace_spans": mock_trace,
            "root_spans": mock_root,
        }


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


def create_span_data(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    service_name: str,
    name: str,
    start_ns: int,
    duration_ns: int = 100_000,
    span_kind: int = 1,
    status_code: int = 0,
    attributes: dict | None = None,
) -> dict:
    """Create a span dict for Parquet writing."""
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


def write_spans_to_parquet(
    spans: list[dict], base_dir: str, service_name: str
) -> str:
    """Write spans to a Parquet file with date-partitioned path."""
    now = datetime.now(UTC)
    file_name = f"{service_name}_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}.parquet"
    file_path = os.path.join(
        base_dir,
        f"year={now.year}",
        f"month={now.month:02d}",
        f"day={now.day:02d}",
        file_name,
    )

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)
    pq.write_table(table, file_path)

    return file_path


@pytest.fixture
def temp_parquet_dir():
    """Create a temporary directory for Parquet files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def temp_duckdb():
    """Create a temporary DuckDB database with V4 schema."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.duckdb")

        # Create connection and initialize schema
        conn = duckdb.connect(db_path)

        # Read and execute V4 schema files
        schema_dir = Path(__file__).parent.parent / "app" / "db_duckdb" / "schemas"
        conn.execute((schema_dir / "v4_parquet_files.sql").read_text())
        conn.execute((schema_dir / "v4_span_metadata.sql").read_text())
        conn.execute((schema_dir / "v4_services.sql").read_text())
        conn.execute((schema_dir / "v4_failed_files.sql").read_text())
        conn.close()

        # Override settings to use temp database
        from app.config.settings import settings

        original_path = settings.database.duckdb_path
        settings.database.duckdb_path = db_path

        yield db_path

        # Restore original path
        settings.database.duckdb_path = original_path


@pytest.fixture
def populated_v4_env(temp_parquet_dir, temp_duckdb):
    """Create a fully populated V4 environment with multiple services and traces.

    Creates:
    - 2 services: "payment-service" and "order-service"
    - payment-service: 2 traces (one with LLM span, one workflow)
    - order-service: 1 trace (regular spans)

    Returns a dict with trace_ids and span_ids for assertions.
    """
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)

    # ==========================================
    # Payment Service - Trace 1: Regular + LLM
    # ==========================================
    payment_trace1_id = uuid.uuid4().hex
    payment_t1_root_span_id = "pay1_root_00001"
    payment_t1_child1_span_id = "pay1_child_0001"
    payment_t1_child2_span_id = "pay1_child_0002"
    payment_t1_llm_span_id = "pay1_llm_00001"

    payment_trace1_spans = [
        create_span_data(
            trace_id=payment_trace1_id,
            span_id=payment_t1_root_span_id,
            parent_span_id=None,
            service_name="payment-service",
            name="ProcessPayment",
            start_ns=now_ns,
            duration_ns=500_000,
        ),
        create_span_data(
            trace_id=payment_trace1_id,
            span_id=payment_t1_child1_span_id,
            parent_span_id=payment_t1_root_span_id,
            service_name="payment-service",
            name="ValidateCard",
            start_ns=now_ns + 10_000,
            duration_ns=100_000,
        ),
        create_span_data(
            trace_id=payment_trace1_id,
            span_id=payment_t1_child2_span_id,
            parent_span_id=payment_t1_root_span_id,
            service_name="payment-service",
            name="ChargeCard",
            start_ns=now_ns + 120_000,
            duration_ns=200_000,
        ),
        create_span_data(
            trace_id=payment_trace1_id,
            span_id=payment_t1_llm_span_id,
            parent_span_id=payment_t1_child1_span_id,
            service_name="payment-service",
            name="FraudDetectionLLM",
            start_ns=now_ns + 20_000,
            duration_ns=50_000,
            attributes={"openinference.span.kind": "LLM"},
        ),
    ]

    # ==========================================
    # Payment Service - Trace 2: Workflow spans
    # ==========================================
    payment_trace2_id = uuid.uuid4().hex
    payment_t2_wf_span_id = "pay2_wf_000001"
    payment_t2_node1_span_id = "pay2_node_0001"
    payment_t2_node2_span_id = "pay2_node_0002"

    payment_trace2_spans = [
        create_span_data(
            trace_id=payment_trace2_id,
            span_id=payment_t2_wf_span_id,
            parent_span_id=None,
            service_name="payment-service",
            name="RefundWorkflow",
            start_ns=now_ns + 1_000_000,
            duration_ns=300_000,
            attributes={"junjo.span_type": "workflow", "junjo.id": "wf-refund-001"},
        ),
        create_span_data(
            trace_id=payment_trace2_id,
            span_id=payment_t2_node1_span_id,
            parent_span_id=payment_t2_wf_span_id,
            service_name="payment-service",
            name="VerifyRefund",
            start_ns=now_ns + 1_010_000,
            duration_ns=100_000,
            attributes={"junjo.span_type": "node", "junjo.id": "node-verify"},
        ),
        create_span_data(
            trace_id=payment_trace2_id,
            span_id=payment_t2_node2_span_id,
            parent_span_id=payment_t2_wf_span_id,
            service_name="payment-service",
            name="ProcessRefund",
            start_ns=now_ns + 1_120_000,
            duration_ns=150_000,
            attributes={"junjo.span_type": "node", "junjo.id": "node-process"},
        ),
    ]

    # ==========================================
    # Order Service - Trace 1: Regular spans
    # ==========================================
    order_trace1_id = uuid.uuid4().hex
    order_t1_root_span_id = "ord1_root_00001"
    order_t1_child_span_id = "ord1_child_0001"

    order_trace1_spans = [
        create_span_data(
            trace_id=order_trace1_id,
            span_id=order_t1_root_span_id,
            parent_span_id=None,
            service_name="order-service",
            name="CreateOrder",
            start_ns=now_ns + 2_000_000,
            duration_ns=200_000,
        ),
        create_span_data(
            trace_id=order_trace1_id,
            span_id=order_t1_child_span_id,
            parent_span_id=order_t1_root_span_id,
            service_name="order-service",
            name="SaveOrder",
            start_ns=now_ns + 2_050_000,
            duration_ns=100_000,
        ),
    ]

    # ==========================================
    # Write all spans to Parquet files
    # ==========================================
    payment_file1 = write_spans_to_parquet(
        payment_trace1_spans, temp_parquet_dir, "payment-service"
    )
    payment_file2 = write_spans_to_parquet(
        payment_trace2_spans, temp_parquet_dir, "payment-service"
    )
    order_file1 = write_spans_to_parquet(
        order_trace1_spans, temp_parquet_dir, "order-service"
    )

    # ==========================================
    # Index all files into DuckDB
    # ==========================================
    for file_path in [payment_file1, payment_file2, order_file1]:
        file_size = os.path.getsize(file_path)
        file_data = read_parquet_metadata(file_path, file_size)
        v4_repository.index_parquet_file(file_data)

    # Return test data for assertions
    return {
        "parquet_dir": temp_parquet_dir,
        "payment_trace1_id": payment_trace1_id,
        "payment_trace2_id": payment_trace2_id,
        "order_trace1_id": order_trace1_id,
        "payment_t1_root_span_id": payment_t1_root_span_id,
        "payment_t1_child1_span_id": payment_t1_child1_span_id,
        "payment_t1_child2_span_id": payment_t1_child2_span_id,
        "payment_t1_llm_span_id": payment_t1_llm_span_id,
        "payment_t2_wf_span_id": payment_t2_wf_span_id,
        "payment_t2_node1_span_id": payment_t2_node1_span_id,
        "payment_t2_node2_span_id": payment_t2_node2_span_id,
        "order_t1_root_span_id": order_t1_root_span_id,
        "order_t1_child_span_id": order_t1_child_span_id,
    }


# ============================================================================
# Integration Tests - Service Names
# ============================================================================


@pytest.mark.integration
class TestServiceNameListing:
    """Tests for listing service names."""

    @pytest.mark.asyncio
    async def test_get_distinct_service_names(self, populated_v4_env, mock_wal_queries):
        """Should return all indexed service names."""
        services = await otel_repository.get_fused_distinct_service_names()

        assert len(services) == 2
        assert "payment-service" in services
        assert "order-service" in services

    @pytest.mark.asyncio
    async def test_service_names_alphabetical_order(self, populated_v4_env, mock_wal_queries):
        """Service names should be in alphabetical order."""
        services = await otel_repository.get_fused_distinct_service_names()

        assert services[0] == "order-service"
        assert services[1] == "payment-service"


# ============================================================================
# Integration Tests - Root Spans / Traces
# ============================================================================


@pytest.mark.integration
class TestRootSpanListing:
    """Tests for listing root spans (traces)."""

    @pytest.mark.asyncio
    async def test_get_root_spans_for_service(self, populated_v4_env, mock_wal_queries):
        """Should return only root spans for a service."""
        root_spans = await otel_repository.get_fused_root_spans("payment-service")

        # payment-service has 2 traces, each with 1 root span
        assert len(root_spans) == 2

        # All returned spans should be root spans (no parent)
        for span in root_spans:
            assert span["parent_span_id"] is None or span["parent_span_id"] == ""

        # Verify trace IDs
        trace_ids = {span["trace_id"] for span in root_spans}
        assert populated_v4_env["payment_trace1_id"] in trace_ids
        assert populated_v4_env["payment_trace2_id"] in trace_ids

    @pytest.mark.asyncio
    async def test_get_root_spans_different_service(self, populated_v4_env, mock_wal_queries):
        """Should return root spans only for the requested service."""
        root_spans = await otel_repository.get_fused_root_spans("order-service")

        assert len(root_spans) == 1
        assert root_spans[0]["trace_id"] == populated_v4_env["order_trace1_id"]
        assert root_spans[0]["span_id"] == populated_v4_env["order_t1_root_span_id"]

    @pytest.mark.asyncio
    async def test_get_root_spans_empty_for_unknown_service(self, populated_v4_env, mock_wal_queries):
        """Should return empty list for unknown service."""
        root_spans = await otel_repository.get_fused_root_spans("unknown-service")

        assert root_spans == []


# ============================================================================
# Integration Tests - Trace Spans (Child Spans)
# ============================================================================


@pytest.mark.integration
class TestTraceSpanFetching:
    """Tests for fetching all spans in a trace."""

    @pytest.mark.asyncio
    async def test_get_trace_spans_returns_all_spans(self, populated_v4_env, mock_wal_queries):
        """Should return all spans in a trace including children."""
        trace_id = populated_v4_env["payment_trace1_id"]
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        # Trace 1 has 4 spans: root, child1, child2, llm
        assert len(spans) == 4

        span_ids = {span["span_id"] for span in spans}
        assert populated_v4_env["payment_t1_root_span_id"] in span_ids
        assert populated_v4_env["payment_t1_child1_span_id"] in span_ids
        assert populated_v4_env["payment_t1_child2_span_id"] in span_ids
        assert populated_v4_env["payment_t1_llm_span_id"] in span_ids

    @pytest.mark.asyncio
    async def test_get_trace_spans_includes_attributes(self, populated_v4_env, mock_wal_queries):
        """Fetched spans should include parsed attributes."""
        trace_id = populated_v4_env["payment_trace1_id"]
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        # Find the LLM span
        llm_span = next(
            s for s in spans
            if s["span_id"] == populated_v4_env["payment_t1_llm_span_id"]
        )

        # Attributes should be parsed dict
        assert isinstance(llm_span["attributes_json"], dict)
        assert llm_span["attributes_json"].get("openinference.span.kind") == "LLM"

    @pytest.mark.asyncio
    async def test_get_trace_spans_has_correct_structure(self, populated_v4_env, mock_wal_queries):
        """Fetched spans should have all expected fields."""
        trace_id = populated_v4_env["payment_trace1_id"]
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        required_fields = [
            "span_id", "trace_id", "parent_span_id", "service_name", "name",
            "kind", "start_time", "end_time", "status_code", "status_message",
            "attributes_json", "events_json",
        ]

        for span in spans:
            for field in required_fields:
                assert field in span, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_trace_spans_empty_for_unknown_trace(self, populated_v4_env, mock_wal_queries):
        """Should return empty list for unknown trace ID."""
        spans = await otel_repository.get_fused_trace_spans("nonexistent_trace_id_here")

        assert spans == []


# ============================================================================
# Integration Tests - Single Span
# ============================================================================


@pytest.mark.integration
class TestSingleSpanFetching:
    """Tests for fetching a single span by ID."""

    @pytest.mark.asyncio
    async def test_get_span_returns_correct_span(self, populated_v4_env, mock_wal_queries):
        """Should return the specific span."""
        trace_id = populated_v4_env["payment_trace1_id"]
        span_id = populated_v4_env["payment_t1_child1_span_id"]

        span = await otel_repository.get_fused_span(trace_id, span_id)

        assert span is not None
        assert span["span_id"] == span_id
        assert span["trace_id"] == trace_id
        assert span["name"] == "ValidateCard"

    @pytest.mark.asyncio
    async def test_get_span_returns_none_for_unknown(self, populated_v4_env, mock_wal_queries):
        """Should return None for unknown span."""
        trace_id = populated_v4_env["payment_trace1_id"]

        span = await otel_repository.get_fused_span(trace_id, "nonexistent_span")

        assert span is None


# ============================================================================
# Integration Tests - Workflow Spans
# ============================================================================


@pytest.mark.integration
class TestWorkflowSpans:
    """Tests for workflow span filtering."""

    async def test_get_workflow_spans_returns_only_workflows(self, populated_v4_env):
        """Should return only spans with junjo_span_type = 'workflow'."""
        workflow_spans = await otel_repository.get_fused_workflow_spans("payment-service")

        # Only 1 workflow span in payment-service
        assert len(workflow_spans) == 1

        wf_span = workflow_spans[0]
        assert wf_span["span_id"] == populated_v4_env["payment_t2_wf_span_id"]
        assert wf_span["name"] == "RefundWorkflow"
        assert wf_span["junjo_span_type"] == "workflow"
        assert wf_span["junjo_id"] == "wf-refund-001"

    async def test_get_workflow_spans_empty_for_service_without_workflows(self, populated_v4_env):
        """Should return empty list for service with no workflow spans."""
        workflow_spans = await otel_repository.get_fused_workflow_spans("order-service")

        assert workflow_spans == []


# ============================================================================
# Integration Tests - Service Spans
# ============================================================================


@pytest.mark.integration
class TestServiceSpans:
    """Tests for fetching all spans for a service."""

    async def test_get_service_spans_returns_all_spans(self, populated_v4_env):
        """Should return all spans for a service across all traces."""
        spans = await otel_repository.get_fused_service_spans("payment-service")

        # payment-service has: trace1 (4 spans) + trace2 (3 spans) = 7 spans
        assert len(spans) == 7

        # Verify spans from both traces are present
        trace_ids = {span["trace_id"] for span in spans}
        assert populated_v4_env["payment_trace1_id"] in trace_ids
        assert populated_v4_env["payment_trace2_id"] in trace_ids

    async def test_get_service_spans_respects_limit(self, populated_v4_env):
        """Should respect the limit parameter."""
        spans = await otel_repository.get_fused_service_spans("payment-service", limit=3)

        assert len(spans) == 3


# ============================================================================
# Integration Tests - Span Kind Mapping
# ============================================================================


@pytest.mark.integration
class TestSpanKindMapping:
    """Tests for span_kind integer to string mapping."""

    async def test_span_kind_maps_to_string(self, populated_v4_env):
        """span_kind int should be mapped to string name."""
        spans = await otel_repository.get_fused_service_spans("payment-service", limit=1)

        # All test spans were created with span_kind=1 (SERVER)
        assert spans[0]["kind"] == "SERVER"


# ============================================================================
# Integration Tests - Timestamp Formatting
# ============================================================================


@pytest.mark.integration
class TestTimestampFormatting:
    """Tests for timestamp formatting in API responses."""

    async def test_timestamps_are_iso8601_strings(self, populated_v4_env):
        """Timestamps should be ISO8601 formatted strings."""
        spans = await otel_repository.get_fused_service_spans("payment-service", limit=1)

        start_time = spans[0]["start_time"]
        end_time = spans[0]["end_time"]

        # Should be strings, not datetime objects
        assert isinstance(start_time, str)
        assert isinstance(end_time, str)

        # Should contain timezone info
        assert "+00:00" in start_time
        assert "+00:00" in end_time

        # Should be parseable ISO format
        assert "T" in start_time
        assert "T" in end_time
