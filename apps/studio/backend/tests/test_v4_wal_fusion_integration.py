"""V4 Two-Tier Fusion Integration Tests.

Tests the fusion of Cold (Parquet) and Hot (Snapshot) data in V4 queries.
Uses mocked responses to verify merge logic without requiring the Rust
ingestion service infrastructure.

Two-Tier Architecture (Rust Ingestion):
- Cold: Parquet files from WAL flushes (indexed in DuckDB)
- Hot: On-demand Parquet snapshot (from PrepareHotSnapshot RPC)

Test scenarios:
1. Service Names: Merge from both tiers via DataFusion
2. Trace Spans: Merge spans from both sources, deduplicate by span_id
3. Root Spans: Merge root spans from both sources
4. Single Span: Query unified two-tier data

Deduplication: Cold wins when same span_id exists in both tiers.
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
from app.db_duckdb.unified_query import UnifiedSpanQuery
from app.features.otel_spans import repository as otel_repository
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata

# ============================================================================
# Test Data Helpers
# ============================================================================

# Arrow schema matching Rust ingestion
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


def create_hot_snapshot(spans: list[dict], temp_dir: str) -> str:
    """Create a hot snapshot Parquet file (simulates PrepareHotSnapshot result)."""
    if not spans:
        # Empty snapshot
        table = pa.Table.from_pylist([], schema=SPAN_SCHEMA)
    else:
        table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)

    snapshot_path = os.path.join(temp_dir, "hot_snapshot.parquet")
    pq.write_table(table, snapshot_path)
    return snapshot_path


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
    """Create environment for two-tier fusion testing.

    Creates:
    - service-a: In Parquet only (cold data)
    - service-b: In hot snapshot only (not flushed yet)
    - service-c: Root in Parquet, children in hot snapshot (split trace)

    Returns dict with:
    - Trace IDs and span IDs for each service
    - Hot snapshot path containing hot tier spans
    """
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)

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
    # Service C: Split across Parquet and Hot
    # Root span in Parquet, children in hot snapshot
    # ==========================================
    split_trace_id = uuid.uuid4().hex
    split_root_span_id = "split_root_0001"
    split_child1_span_id = "split_child_001"
    split_child2_span_id = "split_child_002"

    # Only root span in Parquet (cold)
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
    # Write Parquet files and index (cold tier)
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
    # Hot Snapshot Data (simulates PrepareHotSnapshot result)
    # ==========================================
    # Service B: Only in hot snapshot
    service_b_trace_id = uuid.uuid4().hex
    service_b_span_id = "svc_b_root_001"

    hot_spans = [
        # Service B root span
        create_span_data(
            trace_id=service_b_trace_id,
            span_id=service_b_span_id,
            parent_span_id=None,
            service_name="service-b",
            name="ServiceBRoot",
            start_ns=now_ns + 2_000_000,
        ),
        # Service C child spans (parent is in cold tier)
        create_span_data(
            trace_id=split_trace_id,
            span_id=split_child1_span_id,
            parent_span_id=split_root_span_id,
            service_name="service-c",
            name="SplitTraceChild1",
            start_ns=now_ns + 1_100_000,
        ),
        create_span_data(
            trace_id=split_trace_id,
            span_id=split_child2_span_id,
            parent_span_id=split_root_span_id,
            service_name="service-c",
            name="SplitTraceChild2",
            start_ns=now_ns + 1_200_000,
        ),
    ]

    hot_snapshot_path = create_hot_snapshot(hot_spans, temp_parquet_dir)

    return {
        "parquet_dir": temp_parquet_dir,
        "hot_snapshot_path": hot_snapshot_path,
        # Service A (cold only)
        "service_a_trace_id": service_a_trace_id,
        "service_a_span_id": service_a_span_id,
        # Service B (hot only)
        "service_b_trace_id": service_b_trace_id,
        "service_b_span_id": service_b_span_id,
        # Split trace
        "split_trace_id": split_trace_id,
        "split_root_span_id": split_root_span_id,
        "split_child1_span_id": split_child1_span_id,
        "split_child2_span_id": split_child2_span_id,
    }


# ============================================================================
# Fusion Tests - Service Names (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestServiceNameFusion:
    """Tests for service name fusion from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_service_names_include_hot_only_service(self, fusion_test_env):
        """Service names should include services only in hot tier."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = fusion_test_env["hot_snapshot_path"]

            services = await otel_repository.get_fused_distinct_service_names()

            # Should have all 3 services
            assert len(services) == 3
            assert "service-a" in services  # Cold only
            assert "service-b" in services  # Hot only
            assert "service-c" in services  # Both tiers

    @pytest.mark.asyncio
    async def test_service_names_deduplicate(self, fusion_test_env):
        """Duplicate service names should be deduplicated."""
        # Create a hot snapshot with only service-c (which is also in cold)
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id=uuid.uuid4().hex,
                span_id="hot_svc_c_span",
                parent_span_id=None,
                service_name="service-c",
                name="HotOnlySpan",
                start_ns=now_ns,
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            services = await otel_repository.get_fused_distinct_service_names()

            # Should be unique and sorted
            assert services == ["service-a", "service-c"]

    @pytest.mark.asyncio
    async def test_service_names_graceful_degradation(self, fusion_test_env):
        """Should return cold services if hot snapshot unavailable."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = None  # Hot tier unavailable

            services = await otel_repository.get_fused_distinct_service_names()

            # Should still have cold tier services
            assert "service-a" in services
            assert "service-c" in services
            # service-b was only in hot tier, so it won't be present
            assert "service-b" not in services


# ============================================================================
# Fusion Tests - Trace Spans (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestTraceSpanFusion:
    """Tests for trace span fusion from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_trace_spans_merge_cold_and_hot(self, fusion_test_env):
        """Should merge spans from cold (Parquet) and hot tiers."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = fusion_test_env["hot_snapshot_path"]

            trace_id = fusion_test_env["split_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            # Should have root (cold) + 2 children (hot)
            assert len(spans) == 3

            span_ids = {s["span_id"] for s in spans}
            assert fusion_test_env["split_root_span_id"] in span_ids
            assert fusion_test_env["split_child1_span_id"] in span_ids
            assert fusion_test_env["split_child2_span_id"] in span_ids

    @pytest.mark.asyncio
    async def test_trace_spans_cold_wins_deduplication(self, fusion_test_env):
        """Cold tier should win if same span exists in hot tier."""
        # Create hot snapshot with duplicate of split_root_span_id but different name
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id=fusion_test_env["split_trace_id"],
                span_id=fusion_test_env["split_root_span_id"],  # Same ID as cold
                parent_span_id=None,
                service_name="service-c",
                name="HOT_VERSION_ROOT",  # Different name to prove cold wins
                start_ns=now_ns,
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            trace_id = fusion_test_env["split_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            # Should have only 1 span (deduplicated)
            assert len(spans) == 1

            # Should be the cold version (original name)
            assert spans[0]["name"] == "SplitTraceRoot"

    @pytest.mark.asyncio
    async def test_trace_spans_hot_only_trace(self, fusion_test_env):
        """Should return hot tier spans for trace not in cold tier."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = fusion_test_env["hot_snapshot_path"]

            trace_id = fusion_test_env["service_b_trace_id"]
            spans = await otel_repository.get_fused_trace_spans(trace_id)

            assert len(spans) == 1
            assert spans[0]["span_id"] == fusion_test_env["service_b_span_id"]


# ============================================================================
# Fusion Tests - Root Spans (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestRootSpanFusion:
    """Tests for root span fusion from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_root_spans_include_hot(self, fusion_test_env):
        """Should include root spans from hot tier."""
        # Create hot snapshot with a new root span for service-c
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id=uuid.uuid4().hex,
                span_id="hot_new_root_01",
                parent_span_id=None,  # Root span
                service_name="service-c",
                name="HotRootSpan",
                start_ns=now_ns,
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            root_spans = await otel_repository.get_fused_root_spans("service-c")

            # Should have cold root + hot root
            assert len(root_spans) == 2

            span_ids = {s["span_id"] for s in root_spans}
            assert fusion_test_env["split_root_span_id"] in span_ids  # Cold
            assert "hot_new_root_01" in span_ids  # Hot


# ============================================================================
# Fusion Tests - Single Span (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestSingleSpanFusion:
    """Tests for single span lookup from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_get_span_from_cold(self, fusion_test_env):
        """Should find span in cold tier."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = None  # Empty hot tier

            trace_id = fusion_test_env["split_trace_id"]
            span_id = fusion_test_env["split_root_span_id"]

            span = await otel_repository.get_fused_span(trace_id, span_id)

            assert span is not None
            assert span["span_id"] == span_id
            assert span["name"] == "SplitTraceRoot"

    @pytest.mark.asyncio
    async def test_get_span_from_hot_fallback(self, fusion_test_env):
        """Should find span in hot tier if not in cold tier."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = fusion_test_env["hot_snapshot_path"]

            trace_id = fusion_test_env["service_b_trace_id"]
            span_id = fusion_test_env["service_b_span_id"]

            span = await otel_repository.get_fused_span(trace_id, span_id)

            assert span is not None
            assert span["span_id"] == span_id

    @pytest.mark.asyncio
    async def test_get_span_not_found(self, fusion_test_env):
        """Should return None if span not in any tier."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = None  # Empty hot tier

            span = await otel_repository.get_fused_span(
                "nonexistent_trace", "nonexistent_span"
            )

            assert span is None


# ============================================================================
# Fusion Tests - Service Spans (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestServiceSpanFusion:
    """Tests for service span fusion from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_service_spans_merge_cold_and_hot(self, fusion_test_env):
        """Should merge spans from cold and hot tiers for a service."""
        # Create hot snapshot with a span for service-c
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id="hot_trace_001",
                span_id="hot_span_001",
                parent_span_id=None,
                service_name="service-c",
                name="HotOnlySpan",
                start_ns=now_ns,
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            spans = await otel_repository.get_fused_service_spans("service-c")

            # Should have cold spans + hot span
            span_ids = {span["span_id"] for span in spans}
            assert fusion_test_env["split_root_span_id"] in span_ids  # Cold
            assert "hot_span_001" in span_ids  # Hot

    @pytest.mark.asyncio
    async def test_service_spans_cold_wins_deduplication(self, fusion_test_env):
        """Should prefer cold span when same span_id exists in hot."""
        # Create hot snapshot with duplicate of cold span but different name
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id=fusion_test_env["split_trace_id"],
                span_id=fusion_test_env["split_root_span_id"],  # Same ID as cold
                parent_span_id=None,
                service_name="service-c",
                name="HotVersionOfSplitRoot",  # Different name
                start_ns=now_ns,
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            spans = await otel_repository.get_fused_service_spans("service-c")

            # Find the span with matching ID
            matching = [
                s
                for s in spans
                if s["span_id"] == fusion_test_env["split_root_span_id"]
            ]
            assert len(matching) == 1
            # Cold version should win (has name "SplitTraceRoot")
            assert matching[0]["name"] == "SplitTraceRoot"


# ============================================================================
# Workflow Span Fusion Tests (Two-Tier Architecture)
# ============================================================================


@pytest.mark.integration
class TestWorkflowSpanFusion:
    """Tests for workflow span fusion from cold and hot tiers."""

    @pytest.mark.asyncio
    async def test_workflow_spans_merge_cold_and_hot(self, fusion_test_env):
        """Should merge workflow spans from cold and hot tiers."""
        # Create hot snapshot with a workflow span for service-c
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)
        hot_spans = [
            create_span_data(
                trace_id="hot_wf_trace",
                span_id="hot_wf_span",
                parent_span_id=None,
                service_name="service-c",
                name="HotWorkflow",
                start_ns=now_ns,
                attributes={"junjo.span_type": "workflow"},
            ),
        ]
        hot_snapshot = create_hot_snapshot(hot_spans, fusion_test_env["parquet_dir"])

        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = hot_snapshot

            spans = await otel_repository.get_fused_workflow_spans("service-c")

            # Should include hot workflow span
            span_ids = {span["span_id"] for span in spans}
            assert "hot_wf_span" in span_ids

    @pytest.mark.asyncio
    async def test_workflow_spans_graceful_degradation(self, fusion_test_env):
        """Should return cold results if hot tier unavailable."""
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock_hot:
            mock_hot.return_value = None  # Hot tier unavailable

            spans = await otel_repository.get_fused_workflow_spans("service-c")

            # Should still work with just cold data
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
        with patch.object(
            otel_repository, "_get_hot_snapshot_path", new_callable=AsyncMock
        ) as mock:
            mock.return_value = None  # Empty hot tier

            spans = await otel_repository.get_fused_root_spans_with_llm("llm-service")

            # Should return the root span from LLM trace
            root_span_ids = {s["span_id"] for s in spans}
            assert llm_test_env["root_span_id"] in root_span_ids
