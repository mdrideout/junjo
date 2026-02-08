"""Concurrency integration test: PrepareHotSnapshot vs FlushWAL (Option 4).

This test targets the historical "empty results" regression window:
1) a trace is ingested
2) a flush moves WAL → cold parquet and deletes WAL segments
3) a concurrent PrepareHotSnapshot call observes WAL empty
4) if `recent_cold_paths` is not visible yet, the backend can return [] for the trace

Option 4 closes this by having ingestion record `recent_cold_paths` while holding
the WAL write lock, so PrepareHotSnapshot can never observe WAL empty without also
seeing the newly-created cold file paths.
"""

import asyncio
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


def _kv(key: str, value: str) -> common_pb2.KeyValue:
    return common_pb2.KeyValue(key=key, value=common_pb2.AnyValue(string_value=value))


def _make_export_request(
    *,
    service_name: str,
    trace_id_hex: str,
    span_ids_hex: list[str],
    payload: str,
    start_ns: int,
) -> trace_service_pb2.ExportTraceServiceRequest:
    trace_id_bytes = bytes.fromhex(trace_id_hex)

    spans = []
    for idx, span_id_hex in enumerate(span_ids_hex):
        spans.append(
            trace_pb2.Span(
                trace_id=trace_id_bytes,
                span_id=bytes.fromhex(span_id_hex),
                name=f"span-{idx}",
                kind=trace_pb2.Span.SpanKind.SPAN_KIND_INTERNAL,
                start_time_unix_nano=start_ns + idx * 1000,
                end_time_unix_nano=start_ns + idx * 1000 + 1_000_000,
                attributes=[_kv("payload", payload)],
            )
        )

    resource = resource_pb2.Resource(attributes=[_kv("service.name", service_name)])
    scope_spans = trace_pb2.ScopeSpans(spans=spans)
    resource_spans = trace_pb2.ResourceSpans(resource=resource, scope_spans=[scope_spans])
    return trace_service_pb2.ExportTraceServiceRequest(resource_spans=[resource_spans])


@pytest.mark.asyncio
async def test_prepare_hot_snapshot_races_with_flush_no_empty_trace_results(rust_ingestion_service):
    service_name = "svc-hot-cold-race"
    trace_id_hex = uuid.uuid4().hex

    # Use an isolated metadata DB so the trace has no indexed cold file paths.
    from app.db_sqlite.metadata import db as metadata_db

    old_metadata_path = getattr(metadata_db, "_db_path", None)

    with tempfile.TemporaryDirectory(prefix="metadata_race_test_") as temp_dir:
        metadata_path = os.path.join(temp_dir, "metadata.db")

        metadata_db.close_connection()
        init_metadata_db(metadata_path)

        old_host = settings.span_ingestion.host
        old_port = settings.span_ingestion.port
        settings.span_ingestion.host = "localhost"
        settings.span_ingestion.port = rust_ingestion_service["internal_port"]

        try:
            # Ingest enough spans to make FlushWAL take long enough that PrepareHotSnapshot
            # is very likely to block on the WAL lock (i.e., actually "race").
            payload = "x" * 256
            expected_span_ids: list[str] = []

            otlp_channel = grpc.aio.insecure_channel(
                f"localhost:{rust_ingestion_service['public_port']}"
            )
            otlp_stub = trace_service_pb2_grpc.TraceServiceStub(otlp_channel)

            start_ns = int(time.time() * 1e9)
            try:
                for _ in range(25):  # 25 * 200 = 5000 spans
                    span_ids = [os.urandom(8).hex() for _ in range(200)]
                    expected_span_ids.extend(span_ids)
                    req = _make_export_request(
                        service_name=service_name,
                        trace_id_hex=trace_id_hex,
                        span_ids_hex=span_ids,
                        payload=payload,
                        start_ns=start_ns,
                    )
                    await otlp_stub.Export(req, metadata=(("x-junjo-api-key", "test-key"),))
            finally:
                await otlp_channel.close()

            # Ensure the trace isn't discoverable via the SQLite metadata index yet.
            assert metadata_repo.get_file_paths_for_trace(trace_id_hex) == []

            # Race FlushWAL with a backend trace query (which calls PrepareHotSnapshot internally).
            from app.features.otel_spans import repository as spans_repo

            spans_repo._ingestion_client = None

            flush_client = IngestionClient(
                host="localhost",
                port=rust_ingestion_service["internal_port"],
            )
            await flush_client.connect()
            try:
                flush_task = asyncio.create_task(flush_client.flush_wal())

                # Give FlushWAL a head start so PrepareHotSnapshot is likely to wait on the WAL lock.
                await asyncio.sleep(0)

                query_task = asyncio.create_task(spans_repo.get_fused_trace_spans(trace_id_hex))

                spans, flush_ok = await asyncio.gather(query_task, flush_task)

                assert flush_ok is True
                assert spans, "no empty-results regression: expected spans during flush/snapshot race"
                assert {s["trace_id"] for s in spans} == {trace_id_hex}

                # Stronger assertion: we should get all ingested spans exactly once.
                got_span_ids = {s["span_id"] for s in spans}
                assert got_span_ids == set(expected_span_ids)
            finally:
                await flush_client.close()

        finally:
            metadata_db.close_connection()
            metadata_db._db_path = old_metadata_path  # type: ignore[attr-defined]
            settings.span_ingestion.host = old_host
            settings.span_ingestion.port = old_port

