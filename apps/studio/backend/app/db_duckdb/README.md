# DuckDB Integration for OTEL Spans

## Status: Phase 6a Complete (Schema & Repository)

DuckDB is used for analytics-optimized storage of OpenTelemetry spans and traces.
Unlike SQLite (used for users/auth), DuckDB excels at analytical queries on large datasets.

---

## ✅ Implemented (Phase 6a)

- **DuckDB connection configuration** (`db_config.py`)
  - Raw duckdb connections for performance
  - `get_connection()` helper function
  - `initialize_tables()` for DDL execution

- **Table schemas** (`schemas/`)
  - `spans_schema.sql` - OTEL spans with Junjo custom fields
  - `state_patches_schema.sql` - Workflow state changes
  - Composite primary key: (trace_id, span_id)
  - Foreign key: state_patches → spans
  - 10 indexes total for query performance

- **Data models** (`models.py`)
  - `Span` - Pydantic model (documentation)
  - `StatePatch` - Pydantic model (documentation)
  - Note: Models for type hints only, not used for ORM

- **Repository** (`repository.py`)
  - `SpanRepository.batch_insert_spans()` - Bulk insert with INSERT OR IGNORE
  - `SpanRepository.batch_insert_state_patches()` - Bulk insert with FK validation
  - Uses raw SQL for performance (duckdb.executemany)

- **Application startup integration**
  - Tables initialized on app startup (`main.py`)
  - Database path: `/dbdata/duckdb/traces.duckdb`
  - Idempotent DDL (CREATE TABLE IF NOT EXISTS)

---

## 📋 TODO: Phase 6b - Span Ingestion (NEXT)

### 1. gRPC Client for Ingestion Service
- **Create**: `app/ingestion_client/client.py`
- **Implement**: `read_spans(start_key, batch_size)` gRPC call
- **Connect to**: `junjo-ai-studio-ingestion:50052`
- **Proto**: Use existing ingestion service proto definitions
- **Config**: Environment variables `INGESTION_GRPC_HOST`, `INGESTION_GRPC_PORT`

### 2. OTLP Span Processor
- **Create**: `app/telemetry/span_processor.py`
- **Functions**:
  ```python
  def process_span(otlp_span, service_name) -> dict:
      """Convert OTLP protobuf span to DuckDB-ready dict."""

  def extract_junjo_attributes(attributes) -> tuple[dict, dict]:
      """Extract Junjo fields and filter from attributes_json."""
      # Returns: (junjo_fields, filtered_attrs)

  def extract_state_patches(events, trace_id, span_id, workflow_id, node_id) -> list[dict]:
      """Extract state patches from 'set_state' events."""

  def convert_otlp_attributes_to_json(attributes) -> dict:
      """Handle 6 OTLP attribute types: string, int, double, bool, array, kvlist, bytes."""
  ```

- **Filtered Junjo Attributes** (remove from `attributes_json`):
  ```python
  FILTERED_JUNJO_ATTRIBUTES = [
      "junjo.workflow_id", "node.id", "junjo.id", "junjo.parent_id",
      "junjo.span_type", "junjo.workflow.state.start",
      "junjo.workflow.state.end", "junjo.workflow.graph_structure",
      "junjo.workflow.store.id"
  ]
  ```

- **Dependencies**:
  - `opentelemetry-proto` - OTLP protobuf definitions
  - Handle timestamp conversion (Unix nano → TIMESTAMPTZ)
  - Handle span kind enum → string ("CLIENT", "SERVER", etc.)

### 3. Background Poller
- **Create**: `app/telemetry/ingestion_poller.py`
- **Pattern**: Async infinite loop with asyncio
  ```python
  async def poll_spans_loop():
      while True:
          try:
              # 1. Read from ingestion service (batch_size=100)
              # 2. Deserialize protobuf (span + resource)
              # 3. Extract service_name from resource
              # 4. Process each span (span_processor.py)
              # 5. Batch insert to DuckDB (repository.py)
              # 6. Update SQLite poller_state table
              await asyncio.sleep(5)  # 5 second interval
          except Exception as e:
              logger.error(f"Poller error: {e}")
              # Continue polling (don't crash)
  ```

- **SQLite Integration**:
  - Create `poller_state` table: `id INTEGER PRIMARY KEY, last_key BLOB`
  - Read last key on startup (resume from crash)
  - UPSERT after each successful batch

- **Lifecycle**:
  - Add to `main.py` lifespan: `asyncio.create_task(poll_spans_loop())`
  - Graceful shutdown: cancel task on app shutdown

### 4. Testing
- **Create**: `app/telemetry/test_span_processor.py`
  - Unit tests for attribute conversion
  - Test OTLP type handling (string, int, double, bool, array, kvlist, bytes)
  - Test Junjo attribute extraction and filtering

- **Create**: `app/telemetry/test_span_service.py`
  - Unit tests for batch processing logic
  - Mock DuckDB repository calls

- **Create**: `tests/test_ingestion_poller.py`
  - Integration test with mock gRPC server
  - Test poller state persistence
  - Test error handling and retry logic

---

## 📋 TODO: Phase 6c - Query Endpoints (LATER)

### 5. Query REST API
- **Create**: `app/features/otel/router.py`
- **Endpoints** (6 total):
  1. `GET /otel/span_service_names` - List distinct service names
  2. `GET /otel/service/{service_name}/root_spans` - Root spans for service
  3. `GET /otel/service/{service_name}/root_spans_filtered` - LLM spans only
  4. `GET /otel/trace/{trace_id}/nested_spans` - All spans in trace
  5. `GET /otel/trace/{trace_id}/span/{span_id}` - Single span
  6. `GET /otel/spans/type/workflow/{service_name}` - Workflow spans

- **Response Models**:
  - Create Pydantic models in `app/features/otel/schemas.py`
  - Use snake_case (Python conventions)
  - Add pagination support (offset/limit)

- **Service Layer**:
  - Create `app/features/otel/service.py`
  - Use raw DuckDB queries (not ORM)
  - Handle JSON operator syntax (`attributes_json ->> 'key'`)

---

## Architecture Reference

**Go Backend DuckDB Implementation** (for reference):
- `/Users/matt/repos/junjo-ai-studio/backend/db_duckdb/` - Schema and config
- `/Users/matt/repos/junjo-ai-studio/backend/telemetry/otel_span_processor.go` - Span processing logic (305 lines)
- `/Users/matt/repos/junjo-ai-studio/backend/api/otel/otel_spans_services.go` - Query endpoints (356 lines)
- `/Users/matt/repos/junjo-ai-studio/backend/main.go` (lines 78-160) - Background poller

**Total DuckDB-related code in Go**: ~1,000 lines

---

## Database Paths

**Development** (docker-compose.dev.yml):
```
JUNJO_DUCKDB_PATH=/dbdata/duckdb/traces.duckdb
```

**Production** (docker-compose.yml):
```
JUNJO_DUCKDB_PATH=/dbdata/duckdb/traces.duckdb
```

**Docker Volume**:
```yaml
volumes:
  - ./.dbdata/duckdb:/dbdata/duckdb
```

---

## Key Design Decisions

1. **Raw SQL vs ORM**: Use raw duckdb connections for performance
   - Bulk inserts are 10x+ faster with `executemany()` vs SQLAlchemy
   - DuckDB handles concurrent connections well
   - ORM overhead not worth it for analytics workload

2. **Idempotent Inserts**: `INSERT OR IGNORE` for duplicate spans
   - Spans identified by composite PK: (trace_id, span_id)
   - Re-processing batches is safe (crash recovery)

3. **Foreign Key Constraints**: state_patches → spans
   - Ensures data integrity
   - Patch insert fails if span doesn't exist

4. **JSON Storage**: Store filtered attributes_json
   - Remove Junjo fields to dedicated columns (indexed)
   - Use DuckDB JSON operators for queries (`->>`, `->`)

5. **Sync Table Init**: `initialize_tables()` is synchronous
   - Runs during app startup (before event loop)
   - Simpler than async DDL execution

---

## Testing Strategy

**Unit Tests**:
- Span processor (attribute conversion, filtering)
- Repository (batch insert logic)

**Integration Tests**:
- gRPC client → ingestion service
- Poller → DuckDB (real database)
- Background task lifecycle

**Manual E2E**:
- Start ingestion service with sample data
- Start Python backend (poller runs)
- Verify spans in DuckDB
- Query via REST API

---

## Next Steps

Run `CURRENT_PLAN.md` in repo root for detailed implementation plan.
