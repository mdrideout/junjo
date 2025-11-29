"""Integration tests for OTLP span processor.

Tests the complete span processing pipeline:
1. Create realistic OTLP protobuf spans
2. Process them through the span processor
3. Verify correct insertion into DuckDB (spans + state patches)

NOTE: V3 architecture tests - DISABLED during V4 refactor.
These tests reference V3 DuckDB schema (spans, state_patches tables).
V4 uses Parquet files + metadata indexing instead.
"""

from datetime import UTC

import pytest
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.db_duckdb.db_config import get_connection
from app.features.span_ingestion.span_processor import (
    convert_attributes_to_json,
    convert_events_to_json,
    convert_kind,
    convert_otlp_timestamp,
    extract_json_attribute,
    extract_string_attribute,
    filter_junjo_attributes,
    process_span_batch,
)

# Skip entire module - V3 tests disabled during V4 refactor
pytestmark = pytest.mark.skip(
    reason="V3 tests disabled: V4 refactor uses Parquet indexing instead of spans/state_patches tables"
)


class TestOTLPTypeConversions:
    """Test OTLP type conversion functions."""

    def test_convert_kind_all_types(self):
        """Test span kind conversion for all OTLP kinds."""
        assert convert_kind(0) == "UNSPECIFIED"
        assert convert_kind(1) == "CLIENT"
        assert convert_kind(2) == "SERVER"
        assert convert_kind(3) == "INTERNAL"
        assert convert_kind(4) == "PRODUCER"
        assert convert_kind(5) == "CONSUMER"
        assert convert_kind(999) == "UNSPECIFIED"  # Unknown

    def test_convert_otlp_timestamp(self):
        """Test nanosecond to datetime conversion."""
        # Test known timestamp
        ts_nano = 1699876543123456789
        dt = convert_otlp_timestamp(ts_nano)

        assert dt.year == 2023
        assert dt.month == 11
        assert dt.day == 13
        assert dt.tzinfo == UTC

        # Precision: should maintain microseconds but lose nanoseconds
        # Note: Floating point division may cause rounding (123456789 ns → 123456 or 123457 μs)
        assert 123456 <= dt.microsecond <= 123457

    def test_extract_string_attribute(self):
        """Test string attribute extraction."""
        attributes = [
            common_pb2.KeyValue(
                key="service.name",
                value=common_pb2.AnyValue(string_value="my-service"),
            ),
            common_pb2.KeyValue(key="http.method", value=common_pb2.AnyValue(string_value="GET")),
        ]

        assert extract_string_attribute(attributes, "service.name") == "my-service"
        assert extract_string_attribute(attributes, "http.method") == "GET"
        assert extract_string_attribute(attributes, "not.exists") == ""

    def test_extract_json_attribute(self):
        """Test JSON attribute extraction with default."""
        attributes = [
            common_pb2.KeyValue(
                key="junjo.workflow.state.start",
                value=common_pb2.AnyValue(string_value='{"counter": 0}'),
            ),
        ]

        assert extract_json_attribute(attributes, "junjo.workflow.state.start") == '{"counter": 0}'
        assert extract_json_attribute(attributes, "not.exists") == "{}"  # Default

    def test_convert_attributes_to_json_all_types(self):
        """Test conversion of all 6 OTLP attribute types to JSON."""
        attributes = [
            # StringValue
            common_pb2.KeyValue(key="string.attr", value=common_pb2.AnyValue(string_value="hello")),
            # IntValue
            common_pb2.KeyValue(key="int.attr", value=common_pb2.AnyValue(int_value=42)),
            # DoubleValue
            common_pb2.KeyValue(key="double.attr", value=common_pb2.AnyValue(double_value=3.13)),
            # BoolValue
            common_pb2.KeyValue(key="bool.attr", value=common_pb2.AnyValue(bool_value=True)),
            # ArrayValue
            common_pb2.KeyValue(
                key="array.attr",
                value=common_pb2.AnyValue(
                    array_value=common_pb2.ArrayValue(
                        values=[
                            common_pb2.AnyValue(string_value="a"),
                            common_pb2.AnyValue(int_value=1),
                            common_pb2.AnyValue(bool_value=False),
                        ]
                    )
                ),
            ),
            # KvlistValue
            common_pb2.KeyValue(
                key="kvlist.attr",
                value=common_pb2.AnyValue(
                    kvlist_value=common_pb2.KeyValueList(
                        values=[
                            common_pb2.KeyValue(
                                key="nested.string",
                                value=common_pb2.AnyValue(string_value="value"),
                            ),
                            common_pb2.KeyValue(
                                key="nested.int", value=common_pb2.AnyValue(int_value=10)
                            ),
                        ]
                    )
                ),
            ),
            # BytesValue
            common_pb2.KeyValue(key="bytes.attr", value=common_pb2.AnyValue(bytes_value=b"Hello")),
        ]

        result = convert_attributes_to_json(attributes)
        import json

        data = json.loads(result)

        assert data["string.attr"] == "hello"
        assert data["int.attr"] == 42
        assert data["double.attr"] == 3.13
        assert data["bool.attr"] is True
        assert data["array.attr"] == ["a", 1, False]
        assert data["kvlist.attr"] == {"nested.string": "value", "nested.int": 10}
        assert data["bytes.attr"] == "48656c6c6f"  # "Hello" in hex

    def test_convert_events_to_json(self):
        """Test span events to JSON conversion."""
        events = [
            trace_pb2.Span.Event(
                name="http.request",
                time_unix_nano=1699876543123456789,
                dropped_attributes_count=0,
                attributes=[
                    common_pb2.KeyValue(
                        key="http.method", value=common_pb2.AnyValue(string_value="GET")
                    ),
                    common_pb2.KeyValue(
                        key="http.status_code", value=common_pb2.AnyValue(int_value=200)
                    ),
                ],
            ),
            trace_pb2.Span.Event(
                name="set_state",
                time_unix_nano=1699876544000000000,
                dropped_attributes_count=0,
                attributes=[
                    common_pb2.KeyValue(
                        key="junjo.state_json_patch",
                        value=common_pb2.AnyValue(
                            string_value='{"op": "add", "path": "/counter", "value": 1}'
                        ),
                    ),
                ],
            ),
        ]

        result = convert_events_to_json(events)
        import json

        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["name"] == "http.request"
        assert data[0]["timeUnixNano"] == 1699876543123456789
        assert data[0]["attributes"]["http.method"] == "GET"
        assert data[1]["name"] == "set_state"

    def test_filter_junjo_attributes(self):
        """Test filtering of Junjo dedicated-column attributes."""
        attributes = [
            common_pb2.KeyValue(key="http.method", value=common_pb2.AnyValue(string_value="GET")),
            common_pb2.KeyValue(key="junjo.id", value=common_pb2.AnyValue(string_value="wf-123")),
            common_pb2.KeyValue(
                key="junjo.span_type", value=common_pb2.AnyValue(string_value="workflow")
            ),
            common_pb2.KeyValue(key="http.status_code", value=common_pb2.AnyValue(int_value=200)),
        ]

        filtered = filter_junjo_attributes(attributes)

        # Should keep http attributes, remove junjo attributes
        assert len(filtered) == 2
        keys = [attr.key for attr in filtered]
        assert "http.method" in keys
        assert "http.status_code" in keys
        assert "junjo.id" not in keys
        assert "junjo.span_type" not in keys


@pytest.mark.integration
class TestSpanProcessorIntegration:
    """Integration tests for complete span processing pipeline."""

    @pytest.fixture(scope="class", autouse=True)
    def setup_duckdb_tables(self):
        """Initialize DuckDB tables before running integration tests."""
        from app.db_duckdb.db_config import initialize_tables

        initialize_tables()
        yield
        # Cleanup: tables will be dropped when DuckDB connection closes

    def create_workflow_span(self) -> trace_pb2.Span:
        """Create a realistic workflow span with Junjo custom attributes."""
        span = trace_pb2.Span()

        # IDs (16 bytes for trace_id would be wrong, should be 32, but keeping for test)
        span.trace_id = bytes.fromhex("0123456789abcdef0123456789abcdef")
        span.span_id = bytes.fromhex("0123456789abcdef")
        span.parent_span_id = b""  # Root span

        span.name = "workflow_execution"
        span.kind = 3  # INTERNAL
        span.start_time_unix_nano = 1699876543123456789
        span.end_time_unix_nano = 1699876544123456789

        # Status
        span.status.code = 1  # OK
        span.status.message = "Workflow completed successfully"

        # Standard OTel attributes
        span.attributes.append(
            common_pb2.KeyValue(key="http.method", value=common_pb2.AnyValue(string_value="POST"))
        )

        # Junjo custom attributes
        span.attributes.append(
            common_pb2.KeyValue(key="junjo.id", value=common_pb2.AnyValue(string_value="wf-abc123"))
        )
        span.attributes.append(
            common_pb2.KeyValue(key="junjo.parent_id", value=common_pb2.AnyValue(string_value=""))
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.span_type", value=common_pb2.AnyValue(string_value="workflow")
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow.state.start",
                value=common_pb2.AnyValue(string_value='{"counter": 0, "items": []}'),
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow.state.end",
                value=common_pb2.AnyValue(string_value='{"counter": 5, "items": ["a", "b"]}'),
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow.graph_structure",
                value=common_pb2.AnyValue(string_value='{"nodes": ["start", "process", "end"]}'),
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.workflow.store.id",
                value=common_pb2.AnyValue(string_value="redis://localhost:6379/0"),
            )
        )

        # Events (state patches)
        span.events.append(
            trace_pb2.Span.Event(
                name="set_state",
                time_unix_nano=1699876543500000000,
                attributes=[
                    common_pb2.KeyValue(
                        key="junjo.state_json_patch",
                        value=common_pb2.AnyValue(
                            string_value='{"op": "add", "path": "/counter", "value": 1}'
                        ),
                    ),
                    common_pb2.KeyValue(
                        key="junjo.store.id",
                        value=common_pb2.AnyValue(string_value="redis://localhost:6379/0"),
                    ),
                ],
            )
        )

        span.flags = 1
        span.trace_state = "vendor=test"

        return span

    def create_node_span(self) -> trace_pb2.Span:
        """Create a realistic node span."""
        span = trace_pb2.Span()

        span.trace_id = bytes.fromhex("0123456789abcdef0123456789abcdef")
        span.span_id = bytes.fromhex("fedcba9876543210")
        span.parent_span_id = bytes.fromhex("0123456789abcdef")  # Parent is workflow

        span.name = "node_execution"
        span.kind = 3  # INTERNAL
        span.start_time_unix_nano = 1699876543200000000
        span.end_time_unix_nano = 1699876543800000000

        span.status.code = 1  # OK

        # Junjo custom attributes for node
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.id", value=common_pb2.AnyValue(string_value="node-xyz789")
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.parent_id", value=common_pb2.AnyValue(string_value="wf-abc123")
            )
        )
        span.attributes.append(
            common_pb2.KeyValue(
                key="junjo.span_type", value=common_pb2.AnyValue(string_value="node")
            )
        )

        return span

    def test_process_workflow_span_end_to_end(self):
        """Test processing a complete workflow span from protobuf to DuckDB."""
        service_name = "test-workflow-service"
        span = self.create_workflow_span()

        # Process span batch
        process_span_batch([(span, service_name)])

        # Verify span was inserted (using simpler queries to avoid pytz requirement)
        with get_connection() as conn:
            # Check span exists and has correct basic fields
            result = conn.execute(
                """SELECT trace_id, span_id, service_name, name, kind,
                          junjo_id, junjo_parent_id, junjo_span_type
                   FROM spans WHERE span_id = ?""",
                (span.span_id.hex(),),
            ).fetchone()

            assert result is not None
            # Check basic fields
            assert result[0] == span.trace_id.hex()  # trace_id
            assert result[1] == span.span_id.hex()  # span_id
            assert result[2] == service_name  # service_name
            assert result[3] == "workflow_execution"  # name
            assert result[4] == "INTERNAL"  # kind

            # Check Junjo custom fields
            assert result[5] == "wf-abc123"  # junjo_id
            assert result[6] == ""  # junjo_parent_id
            assert result[7] == "workflow"  # junjo_span_type

            # Check workflow state JSON fields
            state_result = conn.execute(
                """SELECT junjo_wf_state_start, junjo_wf_state_end
                   FROM spans WHERE span_id = ?""",
                (span.span_id.hex(),),
            ).fetchone()

            import json

            state_start = json.loads(state_result[0])
            assert state_start["counter"] == 0

            state_end = json.loads(state_result[1])
            assert state_end["counter"] == 5

            # Check attributes_json doesn't contain filtered Junjo attributes
            attrs_result = conn.execute(
                "SELECT attributes_json FROM spans WHERE span_id = ?",
                (span.span_id.hex(),),
            ).fetchone()

            attributes = json.loads(attrs_result[0])
            assert "http.method" in attributes  # Should be present
            assert "junjo.id" not in attributes  # Should be filtered
            assert "junjo.span_type" not in attributes  # Should be filtered

    def test_process_state_patches(self):
        """Test that state patches are extracted and inserted."""
        service_name = "test-workflow-service"
        span = self.create_workflow_span()

        # Process span batch
        process_span_batch([(span, service_name)])

        # Verify state patch was inserted
        with get_connection() as conn:
            result = conn.execute(
                """SELECT patch_json, workflow_id, node_id, service_name
                   FROM state_patches
                   WHERE trace_id = ? AND span_id = ?""",
                (span.trace_id.hex(), span.span_id.hex()),
            ).fetchone()

            assert result is not None
            import json

            patch = json.loads(result[0])  # patch_json
            assert patch["op"] == "add"
            assert patch["path"] == "/counter"
            assert patch["value"] == 1

            assert result[1] == "wf-abc123"  # workflow_id (from junjo.id)
            assert result[2] == ""  # node_id (empty for workflow spans)
            assert result[3] == service_name

    def test_process_node_span_end_to_end(self):
        """Test processing a node span."""
        service_name = "test-workflow-service"
        span = self.create_node_span()

        # Process span batch
        process_span_batch([(span, service_name)])

        # Verify span was inserted
        with get_connection() as conn:
            result = conn.execute(
                "SELECT junjo_id, junjo_parent_id, junjo_span_type FROM spans WHERE span_id = ?",
                (span.span_id.hex(),),
            ).fetchone()

            assert result is not None
            assert result[0] == "node-xyz789"  # junjo_id
            assert result[1] == "wf-abc123"  # junjo_parent_id
            assert result[2] == "node"  # junjo_span_type

    def test_process_multiple_spans_in_batch(self):
        """Test processing multiple spans in a single transaction."""
        service_name = "test-workflow-service"
        workflow_span = self.create_workflow_span()
        node_span = self.create_node_span()

        # Process both spans in one batch
        process_span_batch([(workflow_span, service_name), (node_span, service_name)])

        # Verify both were inserted
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM spans WHERE trace_id = ?",
                (workflow_span.trace_id.hex(),),
            ).fetchone()[0]

            assert count == 2  # Both spans should be present

    def test_insert_or_ignore_idempotency(self):
        """Test that re-processing the same span doesn't create duplicates."""
        service_name = "test-workflow-service"
        span = self.create_workflow_span()

        # Process same span twice
        process_span_batch([(span, service_name)])
        process_span_batch([(span, service_name)])

        # Verify only one span exists
        with get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM spans WHERE span_id = ?",
                (span.span_id.hex(),),
            ).fetchone()[0]

            assert count == 1  # Should only have one span, not two

    def test_mixed_service_batch_correctly_tagged(self):
        """Test that spans from different services in the same batch get correct service_name.

        This is a regression test for the cross-service contamination bug where
        all spans in a batch would get the service_name from the first span.
        """
        # Create 3 spans from different services
        span1 = self.create_workflow_span()
        span2 = self.create_node_span()
        span3 = self.create_workflow_span()

        # Change span IDs to make them unique
        span1.span_id = bytes.fromhex("1111000000000001")
        span2.span_id = bytes.fromhex("2222000000000001")
        span3.span_id = bytes.fromhex("3333000000000001")

        # Process all 3 spans in ONE batch with DIFFERENT service names
        # This simulates the bug scenario: concurrent apps sending spans
        process_span_batch(
            [
                (span1, "Junjo Base Example"),
                (span2, "Junjo Deployment Example"),
                (span3, "Another Service"),
            ]
        )

        # Verify EACH span got its CORRECT service_name (not the first span's service_name)
        with get_connection() as conn:
            result1 = conn.execute(
                "SELECT service_name FROM spans WHERE span_id = ?",
                (span1.span_id.hex(),),
            ).fetchone()
            assert result1[0] == "Junjo Base Example"

            result2 = conn.execute(
                "SELECT service_name FROM spans WHERE span_id = ?",
                (span2.span_id.hex(),),
            ).fetchone()
            assert result2[0] == "Junjo Deployment Example"  # NOT "Junjo Base Example"!

            result3 = conn.execute(
                "SELECT service_name FROM spans WHERE span_id = ?",
                (span3.span_id.hex(),),
            ).fetchone()
            assert result3[0] == "Another Service"  # NOT "Junjo Base Example"!


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
