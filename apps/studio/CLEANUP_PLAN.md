# Cleanup / Review Plan (Option 4)

This plan covers the review/cleanup/documentation work after implementing **Option 4**:
the ingestion service is the source of truth for “recent cold” (recently flushed but not-yet-indexed)
Parquet files via `PrepareHotSnapshotResponse.recent_cold_paths`.

## 1) Query correctness + dedup review

### 1.1 Verify correctness for each query shape
- Trace query: `GET /api/v1/observability/traces/{trace_id}/spans`
- Service queries: distinct services / root spans / workflow spans
- Confirm the backend always registers:
  - COLD files from SQLite metadata (indexed)
  - plus `recent_cold_paths` (bridge)
  - plus HOT snapshot (unflushed WAL)

### 1.2 Fix dedup key (correctness)
- Current span-level dedup partitions only by `span_id` (unsafe across multiple traces).
- Update dedup to partition by `(trace_id, span_id)` in:
  - `backend/app/features/otel_spans/datafusion_query.py`

### 1.3 Add targeted tests
- Add tests that cover:
  - “cold beats hot” when the same `(trace_id, span_id)` exists in both tiers
  - “same span_id across different traces does not collapse”

## 2) Dead code + config cleanup

### 2.1 Settings cleanup
- Identify and remove unused settings blocks / fields in:
  - `backend/app/config/settings.py`
- In particular, verify whether these are used anywhere:
  - `IngestionServiceSettings`
  - `SpanIngestionSettings` fields beyond `INGESTION_HOST/INGESTION_PORT`

### 2.2 Remove legacy poller artifacts
- Confirm the legacy poller is not used anywhere (repo-wide search).
- If unused, remove:
  - `backend/app/db_sqlite/poller_state/*`
  - `PollerState` import from `backend/migrations/env.py`
- Greenfield cleanup: remove the `poller_state` table from Alembic migrations entirely.

### 2.3 Repo-wide dead-reference scan
- Ensure there are no remaining references to removed concepts:
  - `NotifyNewParquetFile`
  - backend “recent parquet files” tracker
  - backend-side snapshot cache env vars

## 3) ADR audit + updates (check all ADRs)

### 3.1 Review all ADRs for accuracy
- `docs/adr/*`
- `ingestion/adr/*`

### 3.2 Update expected docs
- Update `docs/adr/001-span-storage-architecture.md`:
  - Query flow should include `recent_cold_paths` as the “flush → index” bridge.
- Confirm `docs/adr/003-sqlite-metadata-index-guardrails.md` and
  `ingestion/adr/001-segmented-wal-architecture.md` match Option 4.

## 4) Non-ADR docs (high-value consistency)

- Update `.env.example`:
  - Remove backend-side snapshot throttling docs (`HOT_SNAPSHOT_CACHE_TTL_SECONDS`)
  - Document ingestion-side tunables:
    - `PREPARE_HOT_SNAPSHOT_CACHE_TTL_MS`
    - `RECENT_COLD_MAX_FILES`
    - `RECENT_COLD_MAX_AGE_SECS`
- Update `README.md`:
  - Ensure the two-tier data flow reflects “recent cold paths” bridging semantics.

## 5) Validation / acceptance criteria

### 5.1 Static checks
- Ingestion:
  - `cargo fmt`
  - `cargo clippy`
  - `cargo test`
- Backend:
  - run backend tests script (`./scripts/run-backend-tests.sh`)
  - run lint/format tools if configured (e.g., `ruff`)

### 5.2 Runtime sanity (local)
- Run the high-concurrency span generator and hammer “latest workflow execution” clicks.
- Verify trace spans requests do not return `[]` for traces that exist during flush windows.

### 5.3 Done checklist
- No remaining references to removed notify/back-end recent tracking.
- Dedup partitions on `(trace_id, span_id)`.
- ADRs + `.env.example` + README all match Option 4.
