"""Integration test: Has-LLM filter supports GenAI semconv (xAI).

The trace list "Has LLM Spans" toggle uses the backend endpoint:
  GET /api/v1/observability/services/{service}/spans/root?has_llm=true

For cold data, the backend relies on the SQLite metadata index table `llm_traces`
to determine whether a trace contains any LLM spans.

This test ensures that traces containing GenAI semantic convention spans
(e.g. xAI SDK spans with gen_ai.provider.name="xai") are included.
"""

import os
import tempfile
import time
import uuid
from pathlib import Path

import grpc
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.config.settings import settings
from app.db_sqlite.metadata import init_metadata_db
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
from app.db_sqlite.metadata import indexer as sqlite_indexer
from app.features.span_ingestion.ingestion_client import IngestionClient

pytestmark = [pytest.mark.requires_ingestion_service, pytest.mark.integration]


def _kv(key: str, value: str) -> common_pb2.KeyValue:
    return common_pb2.KeyValue(key=key, value=common_pb2.AnyValue(string_value=value))


def _make_export_request(
    *,
    service_name: str,
    trace_id_hex: str,
    root_span_id_hex: str,
    llm_span_id_hex: str,
    start_ns: int,
) -> trace_service_pb2.ExportTraceServiceRequest:
    trace_id_bytes = bytes.fromhex(trace_id_hex)

    root_span = trace_pb2.Span(
        trace_id=trace_id_bytes,
        span_id=bytes.fromhex(root_span_id_hex),
        name="root-span",
        kind=trace_pb2.Span.SpanKind.SPAN_KIND_SERVER,
        start_time_unix_nano=start_ns,
        end_time_unix_nano=start_ns + 1_000_000,
    )

    # GenAI semantic conventions span (xAI SDK emits these).
    llm_span = trace_pb2.Span(
        trace_id=trace_id_bytes,
        span_id=bytes.fromhex(llm_span_id_hex),
        parent_span_id=bytes.fromhex(root_span_id_hex),
        name="chat.sample",
        kind=trace_pb2.Span.SpanKind.SPAN_KIND_INTERNAL,
        start_time_unix_nano=start_ns + 10_000,
        end_time_unix_nano=start_ns + 1_010_000,
        attributes=[
            _kv("gen_ai.provider.name", "xai"),
            _kv("gen_ai.operation.name", "chat"),
            _kv("gen_ai.model.name", "grok-4-1-fast-non-reasoning"),
        ],
    )

    resource = resource_pb2.Resource(attributes=[_kv("service.name", service_name)])
    scope_spans = trace_pb2.ScopeSpans(spans=[root_span, llm_span])
    resource_spans = trace_pb2.ResourceSpans(resource=resource, scope_spans=[scope_spans])
    return trace_service_pb2.ExportTraceServiceRequest(resource_spans=[resource_spans])


@pytest.mark.asyncio
async def test_has_llm_filter_includes_genai_xai_traces(rust_ingestion_service):
    service_name = "svc-genai-xai-has-llm"
    trace_id_hex = uuid.uuid4().hex
    root_span_id_hex = os.urandom(8).hex()
    llm_span_id_hex = os.urandom(8).hex()

    # Use an isolated metadata DB so we control indexing in this test.
    from app.db_sqlite.metadata import db as metadata_db

    old_metadata_path = getattr(metadata_db, "_db_path", None)

    with tempfile.TemporaryDirectory(prefix="metadata_genai_test_") as temp_dir:
        metadata_path = os.path.join(temp_dir, "metadata.db")

        metadata_db.close_connection()
        init_metadata_db(metadata_path)

        old_host = settings.span_ingestion.host
        old_port = settings.span_ingestion.port
        settings.span_ingestion.host = "localhost"
        settings.span_ingestion.port = rust_ingestion_service["internal_port"]

        try:
            # Ingest via OTLP.
            start_ns = int(time.time() * 1e9)
            req = _make_export_request(
                service_name=service_name,
                trace_id_hex=trace_id_hex,
                root_span_id_hex=root_span_id_hex,
                llm_span_id_hex=llm_span_id_hex,
                start_ns=start_ns,
            )

            otlp_channel = grpc.aio.insecure_channel(
                f"localhost:{rust_ingestion_service['public_port']}"
            )
            otlp_stub = trace_service_pb2_grpc.TraceServiceStub(otlp_channel)
            try:
                await otlp_stub.Export(req, metadata=(("x-junjo-api-key", "test-key"),))
            finally:
                await otlp_channel.close()

            # Flush to cold Parquet.
            flush_client = IngestionClient(
                host="localhost",
                port=rust_ingestion_service["internal_port"],
            )
            await flush_client.connect()
            try:
                assert await flush_client.flush_wal() is True
            finally:
                await flush_client.close()

            # Find the newly written Parquet file and index it into SQLite metadata.
            parquet_dir = Path(rust_ingestion_service["parquet_dir"])
            parquet_files = list(parquet_dir.rglob("*.parquet"))
            assert parquet_files, "expected at least one parquet file after flush"

            parquet_file = max(parquet_files, key=lambda p: p.stat().st_mtime)
            file_data = read_parquet_metadata(str(parquet_file), parquet_file.stat().st_size)
            sqlite_indexer.index_parquet_file(file_data)

            # Now the has_llm filter should include this trace's root span.
            from app.features.otel_spans import repository as spans_repo

            spans_repo._ingestion_client = None
            root_spans = await spans_repo.get_fused_root_spans_with_llm(service_name, limit=50)

            assert root_spans, "expected root spans for LLM traces"
            assert {s["trace_id"] for s in root_spans} == {trace_id_hex}
            assert {s["span_id"] for s in root_spans} == {root_span_id_hex}

        finally:
            metadata_db.close_connection()
            metadata_db._db_path = old_metadata_path  # type: ignore[attr-defined]
            settings.span_ingestion.host = old_host
            settings.span_ingestion.port = old_port

