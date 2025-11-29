"""Integration tests for OTEL spans query API.

Tests end-to-end workflows: ingestion → storage → HTTP API retrieval.
Uses FastAPI TestClient for real HTTP requests against the API endpoints.

NOTE: V3 architecture tests - DISABLED during V4 refactor.
These tests reference V3 DuckDB schema (spans, state_patches tables).
V4 uses Parquet files + metadata indexing instead.
"""

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.db_duckdb.db_config import get_connection, initialize_tables
from app.features.span_ingestion.span_processor import process_span_batch
from app.main import app

# Skip entire module - V3 tests disabled during V4 refactor
pytestmark = pytest.mark.skip(
    reason="V3 tests disabled: V4 refactor uses Parquet indexing instead of spans/state_patches tables"
)

# ===== FIXTURES =====


@pytest.fixture(scope="module", autouse=True)
def setup_duckdb_tables():
    """Initialize DuckDB tables once per module."""
    initialize_tables()
    yield


@pytest.fixture(autouse=True)
def clean_duckdb():
    """Clean DuckDB tables between tests."""
    with get_connection() as conn:
        conn.execute("DELETE FROM state_patches")
        conn.execute("DELETE FROM spans")
        conn.commit()
    yield


@pytest.fixture
def api_client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def create_workflow_span():
    """Factory for creating realistic workflow OTLP spans."""

    def _create(
        service_name: str = "test-service",
        trace_id: str = "0123456789abcdef0123456789abcdef",
        span_id: str = "0123456789abcdef",
        junjo_id: str = "wf-test-123",
        workflow_id: str = "wf-test-123",
        has_state: bool = True,
    ) -> trace_pb2.Span:
        """Create a workflow span with Junjo attributes.

        Args:
            service_name: Service name for the span.
            trace_id: 32-char hex trace ID.
            span_id: 16-char hex span ID.
            junjo_id: Junjo workflow ID.
            workflow_id: Workflow ID (same as junjo_id for workflows).
            has_state: Include workflow state fields.

        Returns:
            OTLP Span protobuf.
        """
        span = trace_pb2.Span()
        span.trace_id = bytes.fromhex(trace_id)
        span.span_id = bytes.fromhex(span_id)
        span.name = f"workflow_{junjo_id}"
        span.kind = 3  # INTERNAL
        span.start_time_unix_nano = 1699876543000000000
        span.end_time_unix_nano = 1699876544000000000

        # Junjo custom attributes
        span.attributes.append(
            common_pb2.KeyValue(key="junjo.id", value=common_pb2.AnyValue(string_value=junjo_id))
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.span_type", value=common_pb2.AnyValue(string_value="workflow")
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow_id", value=common_pb2.AnyValue(string_value=workflow_id)
            )
        )

        if has_state:
            span.attributes.append(
                common_pb2.KeyValue(
                    key="junjo.workflow.state.start",
                    value=common_pb2.AnyValue(string_value='{"counter": 0}'),
                )
            )
            span.attributes.append(
                common_pb2.KeyValue(
                    key="junjo.workflow.state.end",
                    value=common_pb2.AnyValue(string_value='{"counter": 1}'),
                )
            )
            span.attributes.append(
                common_pb2.KeyValue(
                    key="junjo.workflow.graph_structure",
                    value=common_pb2.AnyValue(string_value='{"nodes": ["node1"]}'),
                )
            )

        # Additional OTLP attributes (should be filtered to attributes_json)
        span.attributes.append(
            common_pb2.KeyValue(key="http.method", value=common_pb2.AnyValue(string_value="POST"))
        )

        return span

    return _create


@pytest.fixture
def create_node_span():
    """Factory for creating node-type OTLP spans."""

    def _create(
        service_name: str = "test-service",
        trace_id: str = "0123456789abcdef0123456789abcdef",
        span_id: str = "abcdef0123456789",
        parent_span_id: str = "0123456789abcdef",
        node_id: str = "node1",
        workflow_id: str = "wf-test-123",
    ) -> trace_pb2.Span:
        """Create a node span (child of workflow span)."""
        span = trace_pb2.Span()
        span.trace_id = bytes.fromhex(trace_id)
        span.span_id = bytes.fromhex(span_id)
        span.parent_span_id = bytes.fromhex(parent_span_id)
        span.name = f"node_{node_id}"
        span.kind = 3  # INTERNAL
        span.start_time_unix_nano = 1699876543100000000
        span.end_time_unix_nano = 1699876543900000000

        # Junjo attributes
        span.attributes.append(
            common_pb2.KeyValue(key="node.id", value=common_pb2.AnyValue(string_value=node_id))
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.span_type", value=common_pb2.AnyValue(string_value="node")
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow_id", value=common_pb2.AnyValue(string_value=workflow_id)
            )
        )

        return span

    return _create


# ===== END-TO-END WORKFLOW TESTS =====


@pytest.mark.integration
class TestEndToEndSpanQuery:
    """Test complete flow: ingestion → storage → API retrieval."""

    def test_ingest_and_query_workflow_span(self, api_client, create_workflow_span):
        """End-to-end: Ingest workflow span → Query via API → Verify data integrity."""
        # 1. Create and ingest workflow span
        span = create_workflow_span(
            service_name="my-service",
            trace_id="aaaabbbbccccddddeeeeffffaabbccdd",
            span_id="aabbccddeeff0011",
            junjo_id="wf-e2e-test",
        )
        process_span_batch([(span, "my-service")])

        # 2. Query via /workflows endpoint
        response = api_client.get("/api/v1/observability/services/my-service/workflows")
        assert response.status_code == 200

        # 3. Verify response structure
        workflows = response.json()
        assert len(workflows) == 1

        # 4. Verify data integrity
        wf = workflows[0]
        assert wf["trace_id"] == "aaaabbbbccccddddeeeeffffaabbccdd"
        assert wf["span_id"] == "aabbccddeeff0011"
        assert wf["service_name"] == "my-service"
        assert wf["junjo_id"] == "wf-e2e-test"
        assert wf["junjo_span_type"] == "workflow"

        # 5. Verify JSON state fields
        assert wf["junjo_wf_state_start"] == {"counter": 0}
        assert wf["junjo_wf_state_end"] == {"counter": 1}
        assert wf["junjo_wf_graph_structure"] == {"nodes": ["node1"]}

        # 6. Verify attributes filtered correctly (http.method in attributes_json)
        assert wf["attributes_json"] is not None
        assert "http.method" in wf["attributes_json"]

    def test_ingest_and_query_trace_hierarchy(
        self, api_client, create_workflow_span, create_node_span
    ):
        """End-to-end: Ingest parent + children → Query trace → Verify hierarchy."""
        trace_id = "bbbbccccddddeeeeffffaabbccddeeee"

        # 1. Create parent workflow span
        parent = create_workflow_span(
            service_name="my-service",
            trace_id=trace_id,
            span_id="aaaa000000000001",
            junjo_id="wf-parent",
        )

        # 2. Create 2 child node spans
        child1 = create_node_span(
            service_name="my-service",
            trace_id=trace_id,
            span_id="bbbb000000000001",
            parent_span_id="aaaa000000000001",
            node_id="node1",
        )
        child2 = create_node_span(
            service_name="my-service",
            trace_id=trace_id,
            span_id="bbbb000000000002",
            parent_span_id="aaaa000000000001",
            node_id="node2",
        )

        # 3. Process batch
        process_span_batch([(parent, "my-service"), (child1, "my-service"), (child2, "my-service")])

        # 4. Query via /traces/{traceId}/spans
        response = api_client.get(f"/api/v1/observability/traces/{trace_id}/spans")
        assert response.status_code == 200

        # 5. Verify all 3 spans returned
        spans = response.json()
        assert len(spans) == 3

        # 6. Verify parent relationships
        span_ids = {s["span_id"] for s in spans}
        assert span_ids == {"aaaa000000000001", "bbbb000000000001", "bbbb000000000002"}

        # Verify children have correct parent
        children = [s for s in spans if s["parent_span_id"] is not None]
        assert len(children) == 2
        assert all(c["parent_span_id"] == "aaaa000000000001" for c in children)

        # Verify parent has no parent
        parent_span = [s for s in spans if s["span_id"] == "aaaa000000000001"][0]
        assert parent_span["parent_span_id"] is None


# ===== API CONTRACT TESTS =====


@pytest.mark.integration
class TestAPIEndpoints:
    """Test each endpoint contract with FastAPI TestClient."""

    def test_list_services_returns_distinct_names(self, api_client, create_workflow_span):
        """Verify /services returns distinct service names alphabetically."""
        # Insert spans from 3 services
        process_span_batch(
            [(create_workflow_span(trace_id="c" * 32, span_id="c" * 16), "service-c")]
        )
        process_span_batch(
            [(create_workflow_span(trace_id="a" * 32, span_id="a" * 16), "service-a")]
        )
        process_span_batch(
            [(create_workflow_span(trace_id="b" * 32, span_id="b" * 16), "service-b")]
        )

        response = api_client.get("/api/v1/observability/services")
        assert response.status_code == 200

        services = response.json()
        assert isinstance(services, list)
        assert len(services) == 3
        assert services == ["service-a", "service-b", "service-c"]  # Alphabetical

    def test_get_service_spans_respects_limit(self, api_client, create_workflow_span):
        """Verify limit parameter correctly constrains results."""
        # Insert 10 spans with different timestamps
        for i in range(10):
            span = create_workflow_span(
                trace_id=f"{i:032x}",
                span_id=f"{i:016x}",
                junjo_id=f"wf-{i}",
            )
            # Modify timestamp to ensure ordering
            span.start_time_unix_nano = 1699876543000000000 + (i * 1000000000)
            process_span_batch([(span, "my-service")])

        # Request with limit=5
        response = api_client.get("/api/v1/observability/services/my-service/spans?limit=5")
        assert response.status_code == 200

        spans = response.json()
        assert len(spans) == 5

        # Verify most recent 5 (highest timestamps)
        span_ids = {s["span_id"] for s in spans}
        expected = {f"{i:016x}" for i in range(5, 10)}  # IDs 5-9 (most recent)
        assert span_ids == expected

    def test_get_root_spans_filters_correctly(
        self, api_client, create_workflow_span, create_node_span
    ):
        """Verify /spans/root only returns spans with parent_span_id=NULL."""
        trace_id = "aaaaaaaabbbbbbbbccccccccdddddddd"

        # Insert 2 root spans
        root1 = create_workflow_span(
            trace_id=trace_id, span_id="aaaa000000000001", junjo_id="root1"
        )
        root2 = create_workflow_span(
            trace_id=trace_id, span_id="aaaa000000000002", junjo_id="root2"
        )

        # Insert 3 child spans
        child1 = create_node_span(
            trace_id=trace_id, span_id="bbbb000000000001", parent_span_id="aaaa000000000001"
        )
        child2 = create_node_span(
            trace_id=trace_id, span_id="bbbb000000000002", parent_span_id="aaaa000000000001"
        )
        child3 = create_node_span(
            trace_id=trace_id, span_id="bbbb000000000003", parent_span_id="aaaa000000000002"
        )

        process_span_batch(
            [
                (root1, "my-service"),
                (root2, "my-service"),
                (child1, "my-service"),
                (child2, "my-service"),
                (child3, "my-service"),
            ]
        )

        # Query root spans only
        response = api_client.get("/api/v1/observability/services/my-service/spans/root")
        assert response.status_code == 200

        root_spans = response.json()
        assert len(root_spans) == 2  # Only root1 and root2

        span_ids = {s["span_id"] for s in root_spans}
        assert span_ids == {"aaaa000000000001", "aaaa000000000002"}

        # Verify all have parent_span_id=NULL
        assert all(s["parent_span_id"] is None for s in root_spans)

    def test_get_root_spans_with_llm_filter(self, api_client, create_workflow_span):
        """Verify has_llm=true filters for traces with LLM spans."""
        # Trace 1: Has LLM span
        span_with_llm = create_workflow_span(
            trace_id="11111111222222223333333344444444",
            span_id="1111222233334444",
            junjo_id="llm-root",
        )
        span_with_llm.attributes.append(
            common_pb2.KeyValue(
                key="openinference.span.kind",
                value=common_pb2.AnyValue(string_value="LLM"),
            )
        )

        # Trace 2: No LLM span
        span_no_llm = create_workflow_span(
            trace_id="55555555666666667777777788888888",
            span_id="5555666677778888",
            junjo_id="no-llm-root",
        )

        process_span_batch([(span_with_llm, "my-service"), (span_no_llm, "my-service")])

        # Query with has_llm=true
        response = api_client.get(
            "/api/v1/observability/services/my-service/spans/root?has_llm=true"
        )
        assert response.status_code == 200

        llm_roots = response.json()
        assert len(llm_roots) == 1
        assert llm_roots[0]["span_id"] == "1111222233334444"

    def test_get_workflow_spans_filters_by_type(
        self, api_client, create_workflow_span, create_node_span
    ):
        """Verify /workflows only returns junjo_span_type='workflow'."""
        # Insert 2 workflow spans
        wf1 = create_workflow_span(trace_id="1" * 32, span_id="1111" + "0" * 12, junjo_id="wf1")
        wf2 = create_workflow_span(trace_id="2" * 32, span_id="2222" + "0" * 12, junjo_id="wf2")

        # Insert 3 node spans
        node1 = create_node_span(trace_id="3" * 32, span_id="3333" + "0" * 12, node_id="n1")
        node2 = create_node_span(trace_id="4" * 32, span_id="4444" + "0" * 12, node_id="n2")
        node3 = create_node_span(trace_id="5" * 32, span_id="5555" + "0" * 12, node_id="n3")

        process_span_batch([(wf1, "my-service"), (wf2, "my-service")])
        process_span_batch([(node1, "my-service"), (node2, "my-service"), (node3, "my-service")])

        # Query workflows
        response = api_client.get("/api/v1/observability/services/my-service/workflows")
        assert response.status_code == 200

        workflows = response.json()
        assert len(workflows) == 2

        # Verify all are workflow type
        assert all(s["junjo_span_type"] == "workflow" for s in workflows)

        span_ids = {s["span_id"] for s in workflows}
        assert span_ids == {"1111" + "0" * 12, "2222" + "0" * 12}

    def test_get_trace_spans_returns_all(self, api_client, create_workflow_span, create_node_span):
        """Verify /traces/{traceId}/spans returns all spans for that trace only."""
        target_trace = "aaaa111122223333444455556666777788"
        other_trace = "bbbb999988887777666655554444333322"

        # Insert 4 spans for target trace
        target_spans = [
            create_workflow_span(trace_id=target_trace, span_id=f"a{i:015x}", junjo_id=f"t{i}")
            for i in range(4)
        ]

        # Insert 2 spans for other trace
        other_spans = [
            create_workflow_span(trace_id=other_trace, span_id=f"b{i:015x}", junjo_id=f"o{i}")
            for i in range(2)
        ]

        process_span_batch([(s, "my-service") for s in target_spans + other_spans])

        # Query target trace
        response = api_client.get(f"/api/v1/observability/traces/{target_trace}/spans")
        assert response.status_code == 200

        spans = response.json()
        assert len(spans) == 4

        # Verify all have correct trace_id
        assert all(s["trace_id"] == target_trace for s in spans)

    def test_get_span_by_id_returns_single(self, api_client, create_workflow_span):
        """Verify /traces/{traceId}/spans/{spanId} returns single span."""
        span = create_workflow_span(
            trace_id="aaabbbcccdddeeefffaabbccddeeaaaa",
            span_id="aaabbbcccdddeeef",
            junjo_id="single-wf",
        )
        process_span_batch([(span, "my-service")])

        # Query specific span
        response = api_client.get(
            "/api/v1/observability/traces/aaabbbcccdddeeefffaabbccddeeaaaa/spans/aaabbbcccdddeeef"
        )
        assert response.status_code == 200

        result = response.json()
        assert isinstance(result, dict)
        assert result["trace_id"] == "aaabbbcccdddeeefffaabbccddeeaaaa"
        assert result["span_id"] == "aaabbbcccdddeeef"
        assert result["junjo_id"] == "single-wf"

    def test_get_span_not_found_returns_null(self, api_client):
        """Verify /traces/{traceId}/spans/{spanId} returns null for non-existent span."""
        response = api_client.get(
            "/api/v1/observability/traces/ffffffffffffffffffffffffffffffff/spans/ffffffffffffffff"
        )
        assert response.status_code == 200
        assert response.json() is None


# ===== DATA INTEGRITY TESTS =====


@pytest.mark.integration
class TestDataIntegrity:
    """Verify data round-trip: ingest → store → retrieve."""

    def test_timestamp_precision_preserved(self, api_client, create_workflow_span):
        """Verify timestamp precision is maintained through round-trip."""
        span = create_workflow_span(
            trace_id="1111222233334444555566667777aaaa",
            span_id="1111222233334444",
        )
        # Set specific nanosecond timestamp
        span.start_time_unix_nano = 1699876543123456789  # Specific microseconds
        span.end_time_unix_nano = 1699876544987654321

        process_span_batch([(span, "my-service")])

        # Query back
        response = api_client.get(
            "/api/v1/observability/traces/1111222233334444555566667777aaaa/spans/1111222233334444"
        )
        result = response.json()

        # Verify timestamp format (ISO 8601 string)
        assert "start_time" in result
        assert "end_time" in result
        assert isinstance(result["start_time"], str)
        assert isinstance(result["end_time"], str)

        # Verify contains expected date/time (microsecond precision acceptable)
        assert "2023-11-13" in result["start_time"]

    def test_json_fields_correctly_serialized(self, api_client, create_workflow_span):
        """Verify complex JSON fields (attributes, events) serialize correctly."""
        span = create_workflow_span(
            trace_id="aaaa222233334444555566667777888899",
            span_id="aaaa222233334444",
        )

        # Add complex attributes (all 6 OTLP types)
        span.attributes.append(
            common_pb2.KeyValue(key="string_attr", value=common_pb2.AnyValue(string_value="test"))
        )
        span.attributes.append(
            common_pb2.KeyValue(key="int_attr", value=common_pb2.AnyValue(int_value=42))
        )
        span.attributes.append(
            common_pb2.KeyValue(key="double_attr", value=common_pb2.AnyValue(double_value=3.13))
        )
        span.attributes.append(
            common_pb2.KeyValue(key="bool_attr", value=common_pb2.AnyValue(bool_value=True))
        )

        # Add event
        event = trace_pb2.Span.Event()
        event.name = "test_event"
        event.time_unix_nano = 1699876543500000000
        event.attributes.append(
            common_pb2.KeyValue(
                key="event_key", value=common_pb2.AnyValue(string_value="event_value")
            )
        )
        span.events.append(event)

        process_span_batch([(span, "my-service")])

        # Query back
        response = api_client.get(
            "/api/v1/observability/traces/aaaa222233334444555566667777888899/spans/aaaa222233334444"
        )
        result = response.json()

        # Verify attributes_json is valid JSON dict
        assert isinstance(result["attributes_json"], dict)
        assert result["attributes_json"]["string_attr"] == "test"
        assert result["attributes_json"]["int_attr"] == 42
        assert result["attributes_json"]["double_attr"] == 3.13
        assert result["attributes_json"]["bool_attr"] is True

        # Verify events_json is valid JSON list
        assert isinstance(result["events_json"], list)
        assert len(result["events_json"]) == 1
        assert result["events_json"][0]["name"] == "test_event"

    def test_workflow_state_fields_preserved(self, api_client, create_workflow_span):
        """Verify workflow state JSON fields are preserved."""
        span = create_workflow_span(
            trace_id="bbbb3333444455556666777788889999aa",
            span_id="bbbb333344445555",
            has_state=True,
        )
        process_span_batch([(span, "my-service")])

        response = api_client.get(
            "/api/v1/observability/traces/bbbb3333444455556666777788889999aa/spans/bbbb333344445555"
        )
        result = response.json()

        # Verify state fields are JSON dicts
        assert isinstance(result["junjo_wf_state_start"], dict)
        assert isinstance(result["junjo_wf_state_end"], dict)
        assert isinstance(result["junjo_wf_graph_structure"], dict)

        assert result["junjo_wf_state_start"] == {"counter": 0}
        assert result["junjo_wf_state_end"] == {"counter": 1}
        assert result["junjo_wf_graph_structure"] == {"nodes": ["node1"]}

    def test_hex_ids_correctly_formatted(self, api_client, create_workflow_span):
        """Verify trace_id and span_id are lowercase hex strings."""
        span = create_workflow_span(
            trace_id="AABBCCDDEEFF00112233445566778899",  # Uppercase input
            span_id="AABBCCDDEEFF0011",
        )
        process_span_batch([(span, "my-service")])

        response = api_client.get(
            "/api/v1/observability/traces/aabbccddeeff00112233445566778899/spans"
        )
        spans = response.json()

        # Verify IDs are lowercase
        assert spans[0]["trace_id"] == "aabbccddeeff00112233445566778899"
        assert spans[0]["span_id"] == "aabbccddeeff0011"


# ===== EDGE CASES & ERROR HANDLING =====


@pytest.mark.integration
class TestEdgeCases:
    """Test boundary conditions and error cases."""

    def test_empty_service_returns_empty_list(self, api_client):
        """Verify querying non-existent service returns empty list, not error."""
        response = api_client.get("/api/v1/observability/services/nonexistent-service/spans")
        assert response.status_code == 200
        assert response.json() == []

    def test_empty_trace_returns_empty_list(self, api_client):
        """Verify querying non-existent trace returns empty list."""
        response = api_client.get(
            "/api/v1/observability/traces/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee/spans"
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_limit_parameter_validation_min(self, api_client):
        """Verify limit parameter validates minimum value."""
        response = api_client.get("/api/v1/observability/services/my-service/spans?limit=0")
        assert response.status_code == 422  # Validation error

    def test_limit_parameter_validation_max(self, api_client):
        """Verify limit parameter validates maximum value."""
        response = api_client.get("/api/v1/observability/services/my-service/spans?limit=10001")
        assert response.status_code == 422  # Exceeds max 10000
