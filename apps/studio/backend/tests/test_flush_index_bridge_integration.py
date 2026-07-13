"""Flush→Index bridge integration test (Option 4).

This test reproduces the historical "No logs found" gap:
1) spans are ingested
2) WAL is flushed to a new cold Parquet file
3) the backend SQLite metadata index has not indexed that file yet
4) WAL is now empty (HOT snapshot may be empty)

Option 4 closes this gap by having ingestion return `recent_cold_paths` from
PrepareHotSnapshot, which the backend temporarily treats as additional cold
query sources until indexing catches up.
"""

import os
import tempfile
import time
import uuid

import grpc
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.config.settings import settings
from app.db_sqlite.metadata import init_metadata_db
from app.db_sqlite.metadata import repository as metadata_repo
from app.features.span_ingestion.ingestion_client import IngestionClient

pytestmark = [pytest.mark.requires_ingestion_service, pytest.mark.integration]


def _make_key_value(key: str, value: str) -> common_pb2.KeyValue:
    return common_pb2.KeyValue(key=key, value=common_pb2.AnyValue(string_value=value))


def _make_export_request(*, service_name: str, trace_id_hex: str) -> tuple[
    trace_service_pb2.ExportTraceServiceRequest,
    str,
    str,
]:
    """Return (request, root_span_id_hex, child_span_id_hex)."""
    trace_id_bytes = bytes.fromhex(trace_id_hex)

    root_span_id_hex = os.urandom(8).hex()
    child_span_id_hex = os.urandom(8).hex()

    start_ns = int(time.time() * 1e9)

    root_span = trace_pb2.Span(
        trace_id=trace_id_bytes,
        span_id=bytes.fromhex(root_span_id_hex),
        name="root-span",
        kind=trace_pb2.Span.SpanKind.SPAN_KIND_SERVER,
        start_time_unix_nano=start_ns,
        end_time_unix_nano=start_ns + 1_000_000,
    )
    child_span = trace_pb2.Span(
        trace_id=trace_id_bytes,
        span_id=bytes.fromhex(child_span_id_hex),
        parent_span_id=bytes.fromhex(root_span_id_hex),
        name="child-span",
        kind=trace_pb2.Span.SpanKind.SPAN_KIND_INTERNAL,
        start_time_unix_nano=start_ns + 1000,
        end_time_unix_nano=start_ns + 1_001_000,
    )

    resource = resource_pb2.Resource(attributes=[_make_key_value("service.name", service_name)])
    scope_spans = trace_pb2.ScopeSpans(spans=[root_span, child_span])
    resource_spans = trace_pb2.ResourceSpans(resource=resource, scope_spans=[scope_spans])

    req = trace_service_pb2.ExportTraceServiceRequest(resource_spans=[resource_spans])
    return req, root_span_id_hex, child_span_id_hex


@pytest.mark.asyncio
async def test_trace_query_bridge_uses_recent_cold_paths(rust_ingestion_service):
    service_name = "svc-flush-index-bridge"
    trace_id_hex = uuid.uuid4().hex

    # Use an isolated metadata DB so the trace has no indexed cold file paths.
    from app.db_sqlite.metadata import db as metadata_db

    old_metadata_path = getattr(metadata_db, "_db_path", None)

    with tempfile.TemporaryDirectory(prefix="metadata_bridge_test_") as temp_dir:
        metadata_path = os.path.join(temp_dir, "metadata.db")

        metadata_db.close_connection()
        init_metadata_db(metadata_path)

        try:
            # Point backend ingestion client at the ephemeral ingestion service.
            old_host = settings.span_ingestion.host
            old_port = settings.span_ingestion.port
            settings.span_ingestion.host = "localhost"
            settings.span_ingestion.port = rust_ingestion_service["internal_port"]

            # Ingest spans via OTLP.
            req, root_span_id_hex, child_span_id_hex = _make_export_request(
                service_name=service_name,
                trace_id_hex=trace_id_hex,
            )
            otlp_channel = grpc.aio.insecure_channel(
                f"localhost:{rust_ingestion_service['public_port']}"
            )
            otlp_stub = trace_service_pb2_grpc.TraceServiceStub(otlp_channel)
            await otlp_stub.Export(req, metadata=(("x-junjo-api-key", "test-key"),))
            await otlp_channel.close()

            # Force a cold flush so WAL becomes empty and the spans exist only in a new cold file.
            ingestion_client = IngestionClient(
                host="localhost",
                port=rust_ingestion_service["internal_port"],
            )
            await ingestion_client.connect()
            try:
                assert await ingestion_client.flush_wal() is True

                # Confirm the trace is not discoverable via the SQLite metadata index yet.
                assert metadata_repo.get_file_paths_for_trace(trace_id_hex) == []

                # Confirm ingestion reports the new cold file via recent_cold_paths while HOT is empty.
                snapshot = await ingestion_client.prepare_hot_snapshot()
                assert snapshot.success is True
                assert snapshot.snapshot_path == "" or snapshot.row_count == 0
                assert snapshot.recent_cold_paths, "expected at least one recent cold file path"
                assert all(os.path.exists(p) for p in snapshot.recent_cold_paths)
                assert all(os.path.getsize(p) > 0 for p in snapshot.recent_cold_paths)

            finally:
                await ingestion_client.close()

            # Now the backend query must still find the trace by using recent_cold_paths.
            from app.features.otel_spans import repository as spans_repo

            spans_repo._ingestion_client = None
            spans = await spans_repo.get_fused_trace_spans(trace_id_hex)

            assert spans, "expected spans to be returned via recent_cold_paths bridge"
            assert {s["span_id"] for s in spans} == {root_span_id_hex, child_span_id_hex}
            assert {s["trace_id"] for s in spans} == {trace_id_hex}

        finally:
            # Restore global singletons to avoid leaking state into other tests.
            metadata_db.close_connection()
            metadata_db._db_path = old_metadata_path  # type: ignore[attr-defined]
            settings.span_ingestion.host = old_host
            settings.span_ingestion.port = old_port

