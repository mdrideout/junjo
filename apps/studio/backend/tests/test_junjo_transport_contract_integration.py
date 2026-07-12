"""Integration tests for the current-Junjo transport contract.

These tests verify that current Junjo OTLP payloads survive:

1. OTLP ingestion into the Rust service
2. hot snapshot Parquet generation
3. backend hot-tier querying
4. flush -> recent_cold_paths bridge querying
5. indexed cold-tier querying
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import grpc
import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc

from app.config.settings import settings
from app.db_sqlite.metadata import db as metadata_db
from app.db_sqlite.metadata import indexer as sqlite_indexer
from app.db_sqlite.metadata import init_metadata_db
from app.features.otel_spans import repository as spans_repo
from app.features.otel_spans.datafusion_query import UnifiedSpanQuery
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
from app.features.span_ingestion.ingestion_client import IngestionClient
from tests.helpers.junjo_fixture_loader import (
    list_junjo_fixture_case_names,
    load_junjo_fixture_case,
)
from tests.helpers.junjo_transport_builders import (
    build_otlp_export_request,
    normalize_api_spans,
    workflow_spans_for_case,
)

pytestmark = [pytest.mark.requires_ingestion_service, pytest.mark.integration]

JUNJO_FIXTURE_CASE_NAMES = list_junjo_fixture_case_names()


def _all_parquet_paths(parquet_dir: str) -> set[str]:
    return {str(path) for path in Path(parquet_dir).rglob("*.parquet")}


@pytest.mark.parametrize("case_name", JUNJO_FIXTURE_CASE_NAMES)
@pytest.mark.asyncio
async def test_current_junjo_payload_survives_hot_bridge_and_indexed_cold(
    rust_ingestion_service,
    case_name,
):
    case = load_junjo_fixture_case(case_name)
    expected_trace_spans = normalize_api_spans(case["spans"])
    expected_workflow_spans = normalize_api_spans(workflow_spans_for_case(case))

    old_metadata_path = getattr(metadata_db, "_db_path", None)
    old_host = settings.span_ingestion.host
    old_port = settings.span_ingestion.port
    new_parquet_paths: list[str] = []

    with tempfile.TemporaryDirectory(prefix=f"junjo_transport_{case_name}_") as temp_dir:
        metadata_path = os.path.join(temp_dir, "metadata.db")

        metadata_db.close_connection()
        init_metadata_db(metadata_path)
        settings.span_ingestion.host = "localhost"
        settings.span_ingestion.port = rust_ingestion_service["internal_port"]
        await spans_repo._reset_ingestion_client()

        try:
            existing_parquet_paths = _all_parquet_paths(rust_ingestion_service["parquet_dir"])
            request = build_otlp_export_request(case)

            otlp_channel = grpc.aio.insecure_channel(
                f"localhost:{rust_ingestion_service['public_port']}"
            )
            otlp_stub = trace_service_pb2_grpc.TraceServiceStub(otlp_channel)
            try:
                await otlp_stub.Export(request, metadata=(("x-junjo-api-key", "test-key"),))
            finally:
                await otlp_channel.close()

            ingestion_client = IngestionClient(
                host="localhost",
                port=rust_ingestion_service["internal_port"],
            )
            await ingestion_client.connect()
            try:
                hot_snapshot = await ingestion_client.prepare_hot_snapshot()
                assert hot_snapshot.success is True
                assert hot_snapshot.snapshot_path
                assert hot_snapshot.row_count >= len(case["spans"])

                snapshot_query = UnifiedSpanQuery()
                snapshot_query.register_hot(hot_snapshot.snapshot_path)
                snapshot_results = snapshot_query.query_spans_two_tier(
                    trace_id=case["trace_id"],
                    order_by="start_time ASC",
                )
                assert normalize_api_spans(snapshot_results) == expected_trace_spans

                hot_trace_results = await spans_repo.get_fused_trace_spans(case["trace_id"])
                assert normalize_api_spans(hot_trace_results) == expected_trace_spans

                hot_workflow_results = await spans_repo.get_fused_workflow_spans(
                    case["service_name"]
                )
                assert normalize_api_spans(hot_workflow_results) == expected_workflow_spans

                assert await ingestion_client.flush_wal() is True

                post_flush_snapshot = await ingestion_client.prepare_hot_snapshot()
                new_parquet_paths = sorted(
                    _all_parquet_paths(rust_ingestion_service["parquet_dir"]) - existing_parquet_paths
                )
                assert new_parquet_paths, "expected a new cold parquet file after flush"
                assert set(new_parquet_paths).issubset(set(post_flush_snapshot.recent_cold_paths))
            finally:
                await ingestion_client.close()

            await spans_repo._reset_ingestion_client()
            bridged_trace_results = await spans_repo.get_fused_trace_spans(case["trace_id"])
            assert normalize_api_spans(bridged_trace_results) == expected_trace_spans

            bridged_workflow_results = await spans_repo.get_fused_workflow_spans(
                case["service_name"]
            )
            assert normalize_api_spans(bridged_workflow_results) == expected_workflow_spans

            for parquet_path in new_parquet_paths:
                file_path = Path(parquet_path)
                file_data = read_parquet_metadata(str(file_path), file_path.stat().st_size)
                sqlite_indexer.index_parquet_file(file_data)

            await spans_repo._reset_ingestion_client()
            cold_trace_results = await spans_repo.get_fused_trace_spans(case["trace_id"])
            assert normalize_api_spans(cold_trace_results) == expected_trace_spans

            cold_workflow_results = await spans_repo.get_fused_workflow_spans(case["service_name"])
            assert normalize_api_spans(cold_workflow_results) == expected_workflow_spans

        finally:
            await spans_repo._reset_ingestion_client()
            metadata_db.close_connection()
            metadata_db._db_path = old_metadata_path  # type: ignore[attr-defined]
            settings.span_ingestion.host = old_host
            settings.span_ingestion.port = old_port
