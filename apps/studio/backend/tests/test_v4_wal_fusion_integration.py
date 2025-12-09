"""V4 WAL Fusion Integration Tests.

Tests the fusion of WAL (hot) and Parquet (cold) data in V4 queries.
Uses mocked WAL responses to verify merge logic without requiring
the full Go ingestion service infrastructure.

Test scenarios:
1. Service Names: Merge from both Parquet and WAL
2. Trace Spans: Merge spans from both sources, deduplicate by span_id
3. Root Spans: Merge root spans from both sources
4. Single Span: Check Parquet first, then WAL
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

# ============================================================================
# Test Data Helpers
# ============================================================================

# Arrow schema matching Go ingestion
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


def create_api_span_dict(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    service_name: str,
    name: str,
    start_time: str,
    end_time: str,
    attributes: dict | None = None,
) -> dict:
    """Create a span dict matching API response format (for WAL mock)."""
    attrs = attributes or {}

    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id or "",
        "service_name": service_name,
        "name": name,
        "kind": "SERVER",
        "start_time": start_time,
        "end_time": end_time,
        "status_code": "0",
        "status_message": "",
        "attributes_json": attrs,
        "events_json": [],
        "links_json": [],
        "trace_flags": 0,
        "trace_state": None,
        "junjo_id": "",
        "junjo_parent_id": "",
        "junjo_span_type": attrs.get("junjo.span_type", ""),
        "junjo_wf_state_start": {},
        "junjo_wf_state_end": {},
        "junjo_wf_graph_structure": {},
        "junjo_wf_store_id": "",
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


# ============================================================================
# Fixtures
# ============================================================================


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
        conn.execute((schema_dir / "v4_file_services.sql").read_text())
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
def fusion_test_env(temp_parquet_dir, temp_duckdb):
    """Create environment for fusion testing.

    Creates:
    - service-a: In Parquet only (flushed)
    - service-b: In WAL only (not flushed yet)
    - service-c: In both Parquet and WAL (partial flush)

    Trace split across sources:
    - trace_split: Root span in Parquet, child spans in WAL
    """
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"

    # ==========================================
    # Service A: Only in Parquet (cold data)
    # ==========================================
    service_a_trace_id = uuid.uuid4().hex
    service_a_span_id = "svc_a_root_001"

    service_a_spans = [
        create_span_data(
            trace_id=service_a_trace_id,
            span_id=service_a_span_id,
            parent_span_id=None,
            service_name="service-a",
            name="ServiceARoot",
            start_ns=now_ns,
            duration_ns=100_000,
        ),
    ]

    # ==========================================
    # Service C: Split across Parquet and WAL
    # Root span in Parquet, children in WAL
    # ==========================================
    split_trace_id = uuid.uuid4().hex
    split_root_span_id = "split_root_0001"
    split_child1_span_id = "split_child_001"
    split_child2_span_id = "split_child_002"

    # Only root span in Parquet
    service_c_parquet_spans = [
        create_span_data(
            trace_id=split_trace_id,
            span_id=split_root_span_id,
            parent_span_id=None,
            service_name="service-c",
            name="SplitTraceRoot",
            start_ns=now_ns + 1_000_000,
            duration_ns=500_000,
        ),
    ]

    # ==========================================
    # Write Parquet files and index
    # ==========================================
    service_a_file = write_spans_to_parquet(
        service_a_spans, temp_parquet_dir, "service-a"
    )
    service_c_file = write_spans_to_parquet(
        service_c_parquet_spans, temp_parquet_dir, "service-c"
    )

    for file_path in [service_a_file, service_c_file]:
        file_size = os.path.getsize(file_path)
        file_data = read_parquet_metadata(file_path, file_size)
        v4_repository.index_parquet_file(file_data)

    # ==========================================
    # WAL Data (to be mocked)
    # ==========================================
    # Service B: Only in WAL
    service_b_trace_id = uuid.uuid4().hex
    service_b_span_id = "svc_b_root_001"

    wal_service_b_span = create_api_span_dict(
        trace_id=service_b_trace_id,
        span_id=service_b_span_id,
        parent_span_id=None,
        service_name="service-b",
        name="ServiceBRoot",
        start_time=now_iso,
        end_time=now_iso,
    )

    # Children of split trace in WAL
    wal_child1 = create_api_span_dict(
        trace_id=split_trace_id,
        span_id=split_child1_span_id,
        parent_span_id=split_root_span_id,
        service_name="service-c",
        name="SplitTraceChild1",
        start_time=now_iso,
        end_time=now_iso,
    )
    wal_child2 = create_api_span_dict(
        trace_id=split_trace_id,
        span_id=split_child2_span_id,
        parent_span_id=split_root_span_id,
        service_name="service-c",
        name="SplitTraceChild2",
        start_time=now_iso,
        end_time=now_iso,
    )

    return {
        "parquet_dir": temp_parquet_dir,
        # Service A (Parquet only)
        "service_a_trace_id": service_a_trace_id,
        "service_a_span_id": service_a_span_id,
        # Service B (WAL only)
        "service_b_trace_id": service_b_trace_id,
        "service_b_span_id": service_b_span_id,
        "wal_service_b_span": wal_service_b_span,
        # Split trace
        "split_trace_id": split_trace_id,
        "split_root_span_id": split_root_span_id,
        "split_child1_span_id": split_child1_span_id,
        "split_child2_span_id": split_child2_span_id,
        "wal_child1": wal_child1,
        "wal_child2": wal_child2,
    }


# ============================================================================
# Fusion Tests - Service Names
# ============================================================================


@pytest.mark.integration
class TestServiceNameFusion:
    """Tests for service name fusion from Parquet and WAL."""

    @pytest.mark.asyncio
    async def test_service_names_include_wal_only_service(self, fusion_test_env):
        """Service names should include services only in WAL."""
        with patch.object(otel_repository, "_get_wal_distinct_service_names", new_callable=AsyncMock) as mock:
            # WAL returns service-b (not in Parquet)
            mock.return_value = ["service-b"]

            services = await otel_repository.get_fused_distinct_service_names()

            # Should have all 3 services
            assert len(services) == 3
            assert "service-a" in services
            assert "service-b" in services
            assert "service-c" in services

    @pytest.mark.asyncio
    async def test_service_names_deduplicate(self, fusion_test_env):
        """Duplicate service names should be deduplicated."""
        with patch.object(otel_repository, "_get_wal_distinct_service_names", new_callable=AsyncMock) as mock:
            # WAL returns service-c which is also in Parquet
            mock.return_value = ["service-c", "service-b"]

            services = await otel_repository.get_fused_distinct_service_names()

            # Should be unique and sorted
            assert services == ["service-a", "service-b", "service-c"]

    @pytest.mark.asyncio
    async def test_service_names_graceful_degradation(self, fusion_test_env):
        """Should return Parquet services if WAL query fails."""
        # The _get_wal_distinct_service_names function already catches exceptions and returns []
        # So we mock it to return an empty list (simulating graceful degradation)
        with patch.object(otel_repository, "_get_wal_distinct_service_names", new_callable=AsyncMock) as mock:
            # WAL query returns empty (simulating failure that was caught)
            mock.return_value = []

            services = await otel_repository.get_fused_distinct_service_names()

            # Should still have Parquet services
            assert "service-a" in services
            assert "service-c" in services
            # service-b is WAL-only, so it won't be present
            assert "service-b" not in services


# ============================================================================
# Fusion Tests - Trace Spans
# ============================================================================


@pytest.mark.integration
class TestTraceSpanFusion:
    """Tests for trace span fusion from Parquet and WAL."""

    @pytest.mark.asyncio
    async def test_trace_spans_merge_parquet_and_wal(self, fusion_test_env):
        """Should merge spans from Parquet (root) and WAL (children)."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            # WAL returns child spans not in Parquet
            mock.return_value = [
                fusion_test_env["wal_child1"],
                fusion_test_env["wal_child2"],
            ]

            trace_id = fusion_test_env["split_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            # Should have root (Parquet) + 2 children (WAL)
            assert len(spans) == 3

            span_ids = {s["span_id"] for s in spans}
            assert fusion_test_env["split_root_span_id"] in span_ids
            assert fusion_test_env["split_child1_span_id"] in span_ids
            assert fusion_test_env["split_child2_span_id"] in span_ids

    @pytest.mark.asyncio
    async def test_trace_spans_parquet_wins_deduplication(self, fusion_test_env):
        """Parquet should win if same span exists in both sources."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            # WAL also returns the root span (duplicate)
            wal_duplicate_root = create_api_span_dict(
                trace_id=fusion_test_env["split_trace_id"],
                span_id=fusion_test_env["split_root_span_id"],
                parent_span_id=None,
                service_name="service-c",
                name="WAL_VERSION_ROOT",  # Different name to prove Parquet wins
                start_time="2024-01-01T00:00:00.000000+00:00",
                end_time="2024-01-01T00:00:00.000000+00:00",
            )
            mock.return_value = [wal_duplicate_root]

            trace_id = fusion_test_env["split_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            # Should have only 1 span (deduplicated)
            assert len(spans) == 1

            # Should be the Parquet version (original name)
            assert spans[0]["name"] == "SplitTraceRoot"

    @pytest.mark.asyncio
    async def test_trace_spans_wal_only_trace(self, fusion_test_env):
        """Should return WAL spans for trace not in Parquet."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            # WAL returns spans for service-b trace
            mock.return_value = [fusion_test_env["wal_service_b_span"]]

            trace_id = fusion_test_env["service_b_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            assert len(spans) == 1
            assert spans[0]["span_id"] == fusion_test_env["service_b_span_id"]


# ============================================================================
# Fusion Tests - Root Spans
# ============================================================================


@pytest.mark.integration
class TestRootSpanFusion:
    """Tests for root span fusion from Parquet and WAL."""

    @pytest.mark.asyncio
    async def test_root_spans_include_wal(self, fusion_test_env):
        """Should include root spans from WAL."""
        with patch.object(otel_repository, "_get_wal_root_spans", new_callable=AsyncMock) as mock:
            # WAL returns root span for service-c
            wal_root = create_api_span_dict(
                trace_id=uuid.uuid4().hex,
                span_id="wal_new_root_01",
                parent_span_id=None,
                service_name="service-c",
                name="WALRootSpan",
                start_time="2024-12-01T00:00:00.000000+00:00",
                end_time="2024-12-01T00:00:00.000000+00:00",
            )
            mock.return_value = [wal_root]

            root_spans = await otel_repository.get_fused_root_spans("service-c")

            # Should have Parquet root + WAL root
            assert len(root_spans) == 2

            span_ids = {s["span_id"] for s in root_spans}
            assert fusion_test_env["split_root_span_id"] in span_ids
            assert "wal_new_root_01" in span_ids


# ============================================================================
# Fusion Tests - Single Span
# ============================================================================


@pytest.mark.integration
class TestSingleSpanFusion:
    """Tests for single span lookup from Parquet or WAL."""

    @pytest.mark.asyncio
    async def test_get_span_from_parquet(self, fusion_test_env):
        """Should find span in Parquet."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            mock.return_value = []

            trace_id = fusion_test_env["split_trace_id"]
            span_id = fusion_test_env["split_root_span_id"]

            span = await otel_repository.get_fused_span(trace_id, span_id)

            assert span is not None
            assert span["span_id"] == span_id
            assert span["name"] == "SplitTraceRoot"

    @pytest.mark.asyncio
    async def test_get_span_from_wal_fallback(self, fusion_test_env):
        """Should find span in WAL if not in Parquet."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            # WAL returns the span
            mock.return_value = [fusion_test_env["wal_service_b_span"]]

            trace_id = fusion_test_env["service_b_trace_id"]
            span_id = fusion_test_env["service_b_span_id"]

            span = await otel_repository.get_fused_span(trace_id, span_id)

            assert span is not None
            assert span["span_id"] == span_id

    @pytest.mark.asyncio
    async def test_get_span_not_found(self, fusion_test_env):
        """Should return None if span not in Parquet or WAL."""
        with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock:
            mock.return_value = []

            span = await otel_repository.get_fused_span("nonexistent_trace", "nonexistent_span")

            assert span is None


# ============================================================================
# Service Span Fusion Tests
# ============================================================================


@pytest.mark.integration
class TestServiceSpanFusion:
    """Tests for service span fusion from Parquet and WAL."""

    @pytest.mark.asyncio
    async def test_service_spans_merge_parquet_and_wal(self, fusion_test_env):
        """Should merge spans from both Parquet and WAL for a service."""
        with patch.object(otel_repository, "_get_wal_spans_by_service", new_callable=AsyncMock) as mock:
            # WAL returns a span for service-c (same service as Parquet split trace)
            wal_span = create_api_span_dict(
                trace_id="wal_trace_001",
                span_id="wal_span_001",
                parent_span_id=None,
                service_name="service-c",
                name="WALOnlySpan",
                start_time="2025-11-30T06:00:00.000000+00:00",
                end_time="2025-11-30T06:00:00.001000+00:00",
            )
            mock.return_value = [wal_span]

            spans = await otel_repository.get_fused_service_spans("service-c")

            # Should have Parquet spans + WAL span
            span_ids = {span["span_id"] for span in spans}
            assert fusion_test_env["split_root_span_id"] in span_ids  # Parquet
            assert "wal_span_001" in span_ids  # WAL

    @pytest.mark.asyncio
    async def test_service_spans_parquet_wins_deduplication(self, fusion_test_env):
        """Should prefer Parquet span when same span_id exists in both."""
        with patch.object(otel_repository, "_get_wal_spans_by_service", new_callable=AsyncMock) as mock:
            # WAL returns same span that's in Parquet but with different name
            wal_duplicate = create_api_span_dict(
                trace_id=fusion_test_env["split_trace_id"],
                span_id=fusion_test_env["split_root_span_id"],  # Same ID as Parquet
                parent_span_id=None,
                service_name="service-c",
                name="WALVersionOfSplitRoot",  # Different name
                start_time="2025-11-30T05:00:00.000000+00:00",
                end_time="2025-11-30T05:00:00.001000+00:00",
            )
            mock.return_value = [wal_duplicate]

            spans = await otel_repository.get_fused_service_spans("service-c")

            # Find the span with matching ID
            matching = [s for s in spans if s["span_id"] == fusion_test_env["split_root_span_id"]]
            assert len(matching) == 1
            # Parquet version should win (has name "SplitTraceRoot")
            assert matching[0]["name"] == "SplitTraceRoot"


# ============================================================================
# Workflow Span Fusion Tests
# ============================================================================


@pytest.mark.integration
class TestWorkflowSpanFusion:
    """Tests for workflow span fusion from Parquet and WAL."""

    @pytest.mark.asyncio
    async def test_workflow_spans_merge_parquet_and_wal(self, fusion_test_env):
        """Should merge workflow spans from both Parquet and WAL."""
        with patch.object(otel_repository, "_get_wal_workflow_spans", new_callable=AsyncMock) as mock:
            # WAL returns a workflow span for service-c
            wal_workflow = create_api_span_dict(
                trace_id="wal_wf_trace",
                span_id="wal_wf_span",
                parent_span_id=None,
                service_name="service-c",
                name="WALWorkflow",
                start_time="2025-11-30T06:00:00.000000+00:00",
                end_time="2025-11-30T06:00:00.001000+00:00",
                attributes={"junjo.span_type": "workflow"},
            )
            mock.return_value = [wal_workflow]

            spans = await otel_repository.get_fused_workflow_spans("service-c")

            # Should include WAL workflow span
            span_ids = {span["span_id"] for span in spans}
            assert "wal_wf_span" in span_ids

    @pytest.mark.asyncio
    async def test_workflow_spans_graceful_degradation(self, fusion_test_env):
        """Should return Parquet results if WAL query fails."""
        with patch.object(otel_repository, "_get_wal_workflow_spans", new_callable=AsyncMock) as mock:
            mock.return_value = []  # WAL returns nothing

            spans = await otel_repository.get_fused_workflow_spans("service-c")

            # Should still work with just Parquet data
            assert isinstance(spans, list)


# ============================================================================
# LLM Span Index Tests
# ============================================================================


@pytest.mark.integration
class TestLLMSpanIndexing:
    """Tests for LLM span indexing (openinference_span_kind)."""

    @pytest.fixture
    def llm_test_env(self, temp_parquet_dir, temp_duckdb):
        """Create test environment with LLM spans indexed."""
        # Create trace with LLM span
        llm_trace_id = str(uuid.uuid4()).replace("-", "")
        llm_span_id = str(uuid.uuid4()).replace("-", "")[:16]
        root_span_id = str(uuid.uuid4()).replace("-", "")[:16]

        base_time_ns = int(datetime.now(UTC).timestamp() * 1_000_000_000)

        # Root span (not LLM)
        root_span = create_span_data(
            trace_id=llm_trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            service_name="llm-service",
            name="LLMRequest",
            start_ns=base_time_ns,
        )

        # LLM span with openinference.span.kind = 'LLM'
        llm_span = create_span_data(
            trace_id=llm_trace_id,
            span_id=llm_span_id,
            parent_span_id=root_span_id,
            service_name="llm-service",
            name="ChatCompletion",
            start_ns=base_time_ns + 1000,
            attributes={"openinference.span.kind": "LLM", "llm.model_name": "gpt-4"},
        )

        # Non-LLM trace
        non_llm_trace_id = str(uuid.uuid4()).replace("-", "")
        non_llm_span_id = str(uuid.uuid4()).replace("-", "")[:16]

        non_llm_span = create_span_data(
            trace_id=non_llm_trace_id,
            span_id=non_llm_span_id,
            parent_span_id=None,
            service_name="llm-service",
            name="RegularRequest",
            start_ns=base_time_ns + 2000,
        )

        # Write to Parquet using existing helper
        parquet_file = write_spans_to_parquet(
            [root_span, llm_span, non_llm_span],
            temp_parquet_dir,
            "llm-service",
        )

        # Index the file
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        return {
            "llm_trace_id": llm_trace_id,
            "llm_span_id": llm_span_id,
            "root_span_id": root_span_id,
            "non_llm_trace_id": non_llm_trace_id,
        }

    def test_llm_trace_ids_indexed(self, llm_test_env):
        """LLM trace IDs should be efficiently queryable."""
        llm_trace_ids = v4_repository.get_llm_trace_ids("llm-service", limit=100)

        # Should find the LLM trace
        assert llm_test_env["llm_trace_id"] in llm_trace_ids

        # Should NOT find the non-LLM trace
        assert llm_test_env["non_llm_trace_id"] not in llm_trace_ids

    @pytest.mark.asyncio
    async def test_fused_root_spans_with_llm(self, llm_test_env):
        """Should return only root spans from LLM traces (fused)."""
        with patch.object(otel_repository, "_get_wal_root_spans", new_callable=AsyncMock) as mock_root:
            with patch.object(otel_repository, "_get_wal_spans_by_trace", new_callable=AsyncMock) as mock_trace:
                mock_root.return_value = []
                mock_trace.return_value = []

                spans = await otel_repository.get_fused_root_spans_with_llm("llm-service")

                # Should return the root span from LLM trace
                root_span_ids = {s["span_id"] for s in spans}
                assert llm_test_env["root_span_id"] in root_span_ids
