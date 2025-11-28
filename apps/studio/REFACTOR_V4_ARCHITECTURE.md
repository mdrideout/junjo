# Junjo AI Studio: OpenTelemetry Ingestion Architecture

This document outlines a refactor from the existing architecture to V4.

This is a greenfield project and backwards compatibility and migrations are not required. Existing data and databases will be wiped for a fresh install for v4.

## Executive Summary

A memory-efficient, self-hosted OpenTelemetry span ingestion and analysis system designed for AI application observability. The architecture separates concerns between real-time ingestion (Go + SQLite), historical storage (local filesystem or S3 + Parquet), metadata indexing (Python + DuckDB), and semantic search (LanceDB).

**Target Environment**: Self-hosted deployments on resource-constrained VMs (1GB+ RAM)

**Primary Use Case**: Debugging and analyzing AI agent workflows, LLM interactions, and RAG pipelines

**Storage Philosophy**: Local filesystem by default for simplicity; S3-compatible storage available for cloud deployments or horizontal scaling.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              AI Application                                          │
│                         (Instrumented with OTEL SDK)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ OTLP gRPC (Port 4317)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           Go Ingestion Service                                       │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                         SQLite (WAL Mode)                                  │    │
│   │                                                                            │    │
│   │   • Live span buffer (unflushed data)                                     │    │
│   │   • Indexed by: span_id, trace_id, service_name, start_time              │    │
│   │   • Queryable via gRPC API                                                │    │
│   │   • Automatic TTL cleanup after flush                                     │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                       │                                             │
│                                       │ Flush (time/size trigger)                   │
│                                       ▼                                             │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                      Apache Arrow + Parquet Writer                         │    │
│   │                         (via gocloud.dev/blob)                             │    │
│   │                                                                            │    │
│   │   • Builds Arrow RecordBatches from SQLite rows                           │    │
│   │   • Writes compressed Parquet files                                       │    │
│   │   • Supports local filesystem or S3-compatible storage                    │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   gRPC API:                                                                         │
│   • ListSpans(service, time_range, limit) → span summaries                         │
│   • GetTrace(trace_id) → all spans in trace                                        │
│   • GetSpan(span_id) → full span with attributes                                   │
│   • GetServices() → distinct service names                                          │
│   • StreamSpans(filter) → real-time span stream                                    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ Parquet files
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Storage Layer                                           │
│                    (Local Filesystem default, S3 optional)                          │
│                                                                                      │
│   Default: file:///app/.dbdata/                                                     │
│   Cloud:   s3://bucket/ or gs://bucket/                                             │
│                                                                                      │
│   ├── spans/                                                                        │
│   │   └── year=YYYY/month=MM/day=DD/                                               │
│   │       └── {service}_{timestamp}_{uuid}.parquet                                 │
│   │                                                                                 │
│   ├── vectors/                                                                      │
│   │   └── span_embeddings.lance/                                                   │
│   │                                                                                 │
│   └── _checkpoints/                                                                 │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ Polls for new files
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          Python Backend Service                                      │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                    Background Workers                                      │    │
│   │                                                                            │    │
│   │   Parquet Indexer                    Embedding Generator                  │    │
│   │   • Polls storage for new Parquet    • Polls for unembedded Parquet      │    │
│   │   • Extracts span summaries          • Generates text embeddings          │    │
│   │   • Updates DuckDB metadata          • Writes to LanceDB                  │    │
│   │   • Tracks file→span mappings        • Tracks embedding progress          │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                    DuckDB Metadata Database                                │    │
│   │                                                                            │    │
│   │   • Span summaries (trace_id, span_id, service, name, time, status)      │    │
│   │   • Parquet file registry (file_path, time_range, service, row_count)    │    │
│   │   • Trace-to-file mappings (which files contain which traces)            │    │
│   │   • Pre-aggregated daily statistics                                       │    │
│   │   • Service catalog                                                       │    │
│   │                                                                            │    │
│   │   NOT stored: Full span attributes, events, large payloads               │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                         Query Engines                                      │    │
│   │                        (via pyarrow.fs)                                    │    │
│   │                                                                            │    │
│   │   Apache DataFusion                  LanceDB                              │    │
│   │   • Queries Parquet from storage     • Vector similarity search           │    │
│   │   • Full span data retrieval         • Full-text search                   │    │
│   │   • Complex aggregations             • Returns span_ids + file paths      │    │
│   │   • Partition pruning via metadata   • Reads Lance files from storage     │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   ┌───────────────────────────────────────────────────────────────────────────┐    │
│   │                         Query Orchestrator                                 │    │
│   │                                                                            │    │
│   │   • Merges live data (Go SQLite) with historical data (DuckDB/Storage)   │    │
│   │   • Routes queries to appropriate engine                                  │    │
│   │   • Deduplicates spans across sources                                     │    │
│   │   • Handles semantic search → full data retrieval pipeline               │    │
│   │                                                                            │    │
│   └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   REST/GraphQL API (Port 8000)                                                      │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Frontend Client                                         │
│                                                                                      │
│   • Live trace viewer (polls Go ingestion for real-time updates)                   │
│   • Historical trace browser (queries Python backend)                               │
│   • Dashboard metrics (aggregated from DataFusion)                                  │
│   • Semantic search UI (LanceDB → DataFusion pipeline)                             │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Go Ingestion Service

**Responsibilities**:
- Receive OTLP spans via gRPC
- Buffer spans in SQLite with durability guarantees
- Provide real-time query API for unflushed data
- Flush batches to Parquet on configured storage

**SQLite as WAL**:

SQLite in WAL mode serves as both a write-ahead log and a queryable buffer. This provides:
- Durability (survives crashes)
- Concurrent reads during writes
- Automatic indexing (no manual index maintenance)
- Predictable memory usage (~5-20MB)
- Query throughput sufficient for most workloads (~100K inserts/sec batch mode)

**SQLite Schema**:

| Table | Purpose | Indexes |
|-------|---------|---------|
| `spans` | Full span data for unflushed spans | `span_id` (PK), `trace_id`, `service_name + start_time`, `start_time` |
| `_flush_state` | Tracks last flush timestamp and file | - |

**Key Fields Stored**:
- `span_id`, `trace_id`, `parent_span_id`
- `service_name`, `name` (operation name)
- `start_time`, `end_time`, `duration_ns`
- `status_code`, `span_kind`
- `attributes` (JSON blob)
- `events` (JSON blob)
- `resource_attributes` (JSON blob)

**Flush Logic**:

Flush triggers when ANY condition is met:
1. Time since last flush exceeds threshold
2. Row count exceeds threshold
3. Estimated data size exceeds threshold
4. Manual flush API called

Flush process:
1. Begin transaction
2. SELECT spans WHERE start_time <= flush_cutoff
3. Build Arrow RecordBatches
4. Write Parquet file to storage
5. DELETE flushed spans from SQLite
6. Update `_flush_state`
7. Commit transaction

**gRPC API**:

| Method | Purpose | Data Source |
|--------|---------|-------------|
| `ListSpans` | Paginated span listing | SQLite |
| `GetTrace` | All spans for a trace | SQLite |
| `GetSpan` | Single span with full attributes | SQLite |
| `GetServices` | Distinct service names | SQLite (indexed) |
| `StreamSpans` | Real-time span stream | SQLite + new inserts |
| `GetStats` | Current buffer statistics | SQLite |

**Arrow/Parquet Writing**:

Uses Apache Arrow Go libraries to construct RecordBatches and write Parquet:
- Columnar format optimized for analytical queries
- ZSTD compression for size efficiency
- Row group size tuned for DataFusion (default 122,880 rows)
- Partitioned by date (year/month/day) for query pruning

**Storage Abstraction**:

The system uses a unified storage abstraction layer that supports both local filesystem and cloud object storage. Local filesystem is the default for simplicity; S3-compatible storage is available for cloud deployments or horizontal scaling.

**Storage Libraries**:

| Language | Library | Rationale |
|----------|---------|-----------|
| Go | `gocloud.dev/blob` | URL-based backend selection, first-class S3/GCS support, Google-maintained |
| Go | `apache/arrow/go` | Parquet encoding/decoding (composed with blob storage) |
| Python | `pyarrow.fs` | Same Rust `object_store` crate used internally by DataFusion and LanceDB |

Using `pyarrow.fs` ensures zero impedance mismatch with DataFusion and LanceDB, which use the same underlying Rust `object_store` implementation.

**Supported Storage Backends**:

| Provider | URL Scheme | Use Case |
|----------|------------|----------|
| Local filesystem | `file:///app/.dbdata` | Default, self-hosted, single-node |
| AWS S3 | `s3://bucket?region=us-east-1` | Cloud production, multi-node |
| Google Cloud Storage | `gs://bucket` | Cloud production |
| DigitalOcean Spaces | `s3://bucket?endpoint=...` | Cloud production |
| Cloudflare R2 | `s3://bucket?endpoint=...` | Cloud production, free egress |
| Any S3-compatible | `s3://bucket?endpoint=...` | Custom infrastructure |

**Configuration approach**:
- URL-based backend selection (scheme determines backend)
- Single `storage.url` field for all backends
- Environment variables for credentials (never in config files)

---

### 2. Storage Layer

**Directory Structure** (same for local filesystem and S3):

```
{storage_root}/
│
├── spans/
│   └── year={YYYY}/
│       └── month={MM}/
│           └── day={DD}/
│               ├── {service}_{timestamp}_{uuid}.parquet
│               └── ...
│
├── vectors/
│   └── span_embeddings.lance/
│       ├── _versions/
│       ├── _indices/
│       └── data/
│
├── _checkpoints/
│   ├── indexer/
│   │   └── last_processed.json
│   └── embedder/
│       └── last_processed.json
│
├── metadata.duckdb          # DuckDB metadata database
└── spans.db                 # SQLite live buffer
```

For local filesystem: `{storage_root}` = `/app/.dbdata` (inside container)
For S3: `{storage_root}` = `s3://bucket-name`

**Parquet File Naming**:

`{service_name}_{unix_timestamp}_{uuid8}.parquet`

Example: `chat-api_1705329600_a1b2c3d4.parquet`

**Parquet Schema**:

| Column | Type | Notes |
|--------|------|-------|
| `span_id` | STRING | Primary identifier |
| `trace_id` | STRING | Groups related spans |
| `parent_span_id` | STRING | Nullable, for hierarchy |
| `service_name` | STRING | Originating service |
| `name` | STRING | Operation name |
| `span_kind` | INT8 | Internal/Server/Client/Producer/Consumer |
| `start_time` | TIMESTAMP[ns] | Span start |
| `end_time` | TIMESTAMP[ns] | Span end |
| `duration_ns` | INT64 | Computed duration |
| `status_code` | INT8 | Unset/Ok/Error |
| `status_message` | STRING | Error message if applicable |
| `attributes` | MAP<STRING, STRING> | Span attributes |
| `events` | LIST<STRUCT> | Span events with timestamps |
| `resource_attributes` | MAP<STRING, STRING> | Resource metadata |

---

### 3. Python Backend Service

**Responsibilities**:
- Index new Parquet files into metadata database
- Generate vector embeddings for semantic search
- Provide unified query API merging live and historical data
- Execute complex analytical queries via DataFusion
- Manage data retention and cleanup

#### 3.1 Parquet Indexer (Background Worker)

**Process**:
1. Poll storage for Parquet files newer than last checkpoint
2. For each new file:
   - Read Parquet metadata (row count, time range)
   - Read span summaries (lightweight columns only)
   - Insert into DuckDB metadata tables
   - Update file registry
3. Update checkpoint

**Indexed Data** (stored in DuckDB):

| Data | Purpose |
|------|---------|
| Span summaries | Fast list views without storage round-trip |
| Trace-to-file mapping | Know which files to query for a trace |
| File registry | Track indexed files, prevent re-processing |
| Service catalog | Instant DISTINCT service_name queries |
| Daily aggregates | Dashboard metrics without scanning |

**NOT Indexed** (retrieved from storage via DataFusion):
- Full `attributes` map
- Full `events` list
- Full `resource_attributes` map
- Any large payload data

#### 3.2 Embedding Generator (Background Worker)

**Process**:
1. Poll for Parquet files not yet embedded (via checkpoint)
2. For each file:
   - Read spans
   - Construct searchable text from span fields
   - Generate embeddings using sentence-transformers
   - Write to LanceDB table
3. Update checkpoint

**Text Construction for Embedding**:

Concatenate relevant fields for semantic meaning:
- Operation name
- Service name
- Key attributes (configurable list)
- Error messages
- Event names

Example: `"chat-api generate_response model=gpt-4 error=timeout"`

**LanceDB Schema**:

| Column | Type | Purpose |
|--------|------|---------|
| `span_id` | STRING | Link back to span |
| `trace_id` | STRING | Link to trace |
| `file_path` | STRING | Which Parquet file contains full data |
| `text` | STRING | Searchable text that was embedded |
| `vector` | VECTOR[384] | Embedding (dimension depends on model) |
| `start_time` | TIMESTAMP | For time-filtered search |
| `service_name` | STRING | For service-filtered search |

#### 3.3 DuckDB Metadata Database

**Schema**:

**Table: `parquet_files`**
| Column | Type | Purpose |
|--------|------|---------|
| `file_id` | INTEGER PK | Internal ID |
| `file_path` | TEXT UNIQUE | Storage path |
| `service_name` | TEXT | Primary service in file |
| `min_time` | TIMESTAMP | Earliest span time |
| `max_time` | TIMESTAMP | Latest span time |
| `row_count` | INTEGER | Span count |
| `size_bytes` | INTEGER | File size |
| `indexed_at` | TIMESTAMP | When indexed |

**Table: `span_summaries`**
| Column | Type | Purpose |
|--------|------|---------|
| `span_id` | TEXT PK | Span identifier |
| `trace_id` | TEXT | Trace grouping |
| `parent_span_id` | TEXT | Hierarchy |
| `service_name` | TEXT | Service |
| `name` | TEXT | Operation name |
| `start_time` | TIMESTAMP | Span start |
| `duration_ns` | BIGINT | Duration |
| `status_code` | TINYINT | Status |
| `span_kind` | TINYINT | Kind |
| `is_root` | BOOLEAN | True if no parent |
| `file_id` | INTEGER FK | Source file reference |

**Table: `services`**
| Column | Type | Purpose |
|--------|------|---------|
| `service_name` | TEXT PK | Service identifier |
| `first_seen` | TIMESTAMP | First span time |
| `last_seen` | TIMESTAMP | Latest span time |
| `total_spans` | BIGINT | Cumulative count |

**Table: `daily_stats`**
| Column | Type | Purpose |
|--------|------|---------|
| `service_name` | TEXT | Service |
| `day` | DATE | Date |
| `span_count` | BIGINT | Total spans |
| `error_count` | BIGINT | Spans with status=Error |
| `avg_duration_ns` | DOUBLE | Average duration |
| `p50_duration_ns` | DOUBLE | Median duration |
| `p95_duration_ns` | DOUBLE | 95th percentile |
| `p99_duration_ns` | DOUBLE | 99th percentile |
| PRIMARY KEY | | `(service_name, day)` |

**Indexes**:
- `span_summaries(trace_id)`
- `span_summaries(service_name, start_time DESC)`
- `span_summaries(start_time DESC)`
- `span_summaries(is_root, start_time DESC)` - for listing traces
- `parquet_files(min_time, max_time)`

#### 3.4 Query Orchestrator

**Unified Query Flow**:

For any query that may span live and historical data, the backend executes a two-phase fetch and merge:

```
Client Request
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Backend                            │
│                                                              │
│   Phase 1: Parallel Fetch                                   │
│   ┌─────────────────────┐    ┌─────────────────────┐       │
│   │ gRPC to Go Service  │    │ DuckDB Metadata     │       │
│   │ (live spans in      │    │ (span summaries +   │       │
│   │  SQLite buffer)     │    │  file locations)    │       │
│   └──────────┬──────────┘    └──────────┬──────────┘       │
│              │                          │                   │
│              ▼                          ▼                   │
│   ┌─────────────────────┐    ┌─────────────────────┐       │
│   │ Live Spans          │    │ If full data needed:│       │
│   │ (complete data)     │    │ DataFusion → Parquet│       │
│   └──────────┬──────────┘    └──────────┬──────────┘       │
│              │                          │                   │
│              └────────────┬─────────────┘                   │
│                           ▼                                 │
│   Phase 2: Merge                                           │
│   ┌─────────────────────────────────────────────────┐      │
│   │ 1. Combine results by span_id                    │      │
│   │ 2. Deduplicate (live wins if duplicate)          │      │
│   │ 3. Sort by start_time                            │      │
│   │ 4. Return unified result                         │      │
│   └─────────────────────────────────────────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
Client Response (seamless live + historical data)
```

**Query Routing Logic**:

| Query Type | Live Source (Go) | Historical Source | Merge Strategy |
|------------|------------------|-------------------|----------------|
| List recent spans | SQLite via gRPC | DuckDB span_summaries | Union, dedupe by span_id, sort by time |
| Get trace | SQLite via gRPC | DuckDB → DataFusion | Union, dedupe, sort |
| Get span details | SQLite via gRPC | DataFusion → Storage | First found wins (live preferred) |
| List services | SQLite via gRPC | DuckDB services | Union distinct |
| Dashboard stats | Skip (too recent) | DuckDB daily_stats | Direct query |
| Semantic search | Skip | LanceDB → DataFusion | Vector search then fetch |
| Complex analytics | Skip | DataFusion → Storage | Full scan with pruning |

**Deduplication Note**: Spans may exist in both live (SQLite) and historical (Parquet) during the overlap window after flush but before SQLite cleanup. The merge phase deduplicates by `span_id`, preferring live data when duplicates exist.

**DataFusion Query Optimization**:

- Use DuckDB metadata to identify relevant Parquet files
- Register only necessary files with DataFusion
- Leverage partition pruning (year/month/day)
- Push down predicates to Parquet reader

---

### 4. Query Patterns

#### 4.1 Live View (Real-Time Traces)

**User Action**: View latest traces as they arrive

**Flow**:
1. Client polls Go ingestion service via gRPC `ListSpans(limit=50, is_root=true)`
2. Returns immediately with unflushed root spans
3. Client renders trace list
4. Poll interval: 1-5 seconds

**Latency**: <50ms

#### 4.2 Trace Detail View

**User Action**: Click on a trace to see all spans

**Flow**:
1. Client requests trace from Python backend
2. Backend queries Go ingestion for live spans: `GetTrace(trace_id)`
3. Backend queries DuckDB for historical span IDs in this trace
4. If historical spans exist, fetch full data via DataFusion from storage
5. Merge, deduplicate, return

**Latency**: 
- Live only: <50ms
- With historical: 100-300ms

#### 4.3 Span Detail View

**User Action**: Click on a span to see full attributes

**Flow**:
1. Client requests span from Python backend
2. Backend checks if span_id exists in Go SQLite (live)
   - If yes: return full span from SQLite
3. If not in SQLite, look up file_id in DuckDB
4. Query specific Parquet file via DataFusion for full span
5. Return

**Latency**:
- Live: <50ms
- Historical: 50-150ms

#### 4.4 Service List

**User Action**: Load dropdown of available services

**Flow**:
1. Query Go ingestion: `GetServices()`
2. Query DuckDB: `SELECT service_name FROM services`
3. Union and deduplicate
4. Return sorted list

**Latency**: <20ms

#### 4.5 Dashboard Metrics

**User Action**: Load dashboard with charts

**Flow**:
1. For pre-aggregated metrics (daily stats): Query DuckDB directly
2. For custom time ranges or live data: Query DataFusion with targeted file list
3. Return aggregated results

**Latency**:
- Pre-aggregated: <50ms
- Custom DataFusion query: 200ms-2s depending on scope

#### 4.6 Semantic Search

**User Action**: Search "spans where user query sounded angry"

**Flow**:
1. Generate embedding for search query
2. Query LanceDB for similar vectors (returns span_ids + file_paths)
3. Use file_paths to query DataFusion for full span data
4. Return spans ranked by similarity

**Latency**: 200-500ms

#### 4.7 Rebuild Metadata (Admin Action)

**User Action**: Re-sync metadata database from Parquet files

**Flow**:
1. Truncate DuckDB metadata tables (or create fresh database)
2. List all Parquet files in storage
3. Re-run indexer for each file
4. Rebuild aggregates

**Use Case**: Recovery from corruption, schema migration

---

## Configuration Reference

### Go Ingestion Service

```yaml
# OTLP receiver
otlp:
  grpc_port: 4317
  http_port: 4318                    # Optional HTTP endpoint

# SQLite buffer
sqlite:
  path: "/app/.dbdata/spans.db"
  wal_mode: true                     # Always true for concurrent reads
  busy_timeout_ms: 5000
  cache_size_kb: 65536               # 64MB page cache

# Flush settings
flush:
  interval: "1h"                     # Time-based trigger
  max_rows: 100000                   # Row count trigger
  max_size_mb: 100                   # Size estimate trigger
  min_rows: 1000                     # Don't flush tiny batches

# Parquet output
parquet:
  compression: "zstd"                # zstd, snappy, gzip, none
  compression_level: 3               # For zstd: 1-22
  row_group_size: 122880             # Rows per group (DataFusion optimal)
  
# Storage (URL-based backend selection)
storage:
  url: "file:///app/.dbdata"         # Local filesystem (default)
  # url: "s3://bucket?region=us-east-1"              # AWS S3
  # url: "gs://bucket"                                # GCS
  # url: "s3://bucket?endpoint=nyc3.digitaloceanspaces.com"  # DO Spaces
  
  # For S3-compatible backends, credentials via environment variables:
  # STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY
  # Or use IAM roles / IRSA for AWS/GCP

# gRPC API server
api:
  port: 50051
  max_message_size_mb: 16

# Retention (in SQLite, post-flush)
retention:
  keep_flushed_hours: 1              # Keep flushed spans for overlap queries
```

**Storage URL Examples**:

| Backend | URL |
|---------|-----|
| Local filesystem | `file:///app/.dbdata` |
| AWS S3 | `s3://my-bucket?region=us-west-2` |
| GCS | `gs://my-bucket` |
| DigitalOcean Spaces | `s3://my-bucket?endpoint=nyc3.digitaloceanspaces.com` |
| Cloudflare R2 | `s3://my-bucket?endpoint={account}.r2.cloudflarestorage.com` |

### Python Backend Service

```yaml
# API server
api:
  port: 8000
  cors_origins: ["*"]

# Storage (URL-based, same as ingestion service)
storage:
  url: "file:///app/.dbdata"         # Must match ingestion service
  # url: "s3://bucket?region=us-east-1"  # For cloud deployments
  
  # For S3, credentials via environment variables:
  # STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY

# DuckDB metadata
metadata:
  path: "/app/.dbdata/metadata.duckdb"
  memory_limit: "256MB"              # DuckDB memory limit

# Go ingestion connection
ingestion:
  grpc_address: "ingestion:50051"
  timeout_seconds: 30

# Parquet indexer
indexer:
  poll_interval_seconds: 30
  batch_size: 10                     # Files per batch
  checkpoint_path: "/app/.dbdata/_checkpoints/indexer/"

# Embedding generator
embeddings:
  enabled: true
  model: "all-MiniLM-L6-v2"          # Sentence-transformers model
  batch_size: 32                     # Spans per embedding batch
  poll_interval_seconds: 60
  checkpoint_path: "/app/.dbdata/_checkpoints/embedder/"
  
  # Fields to include in embedding text
  text_fields:
    - "name"
    - "service_name"
    - "attributes.http.route"
    - "attributes.db.statement"
    - "attributes.error.message"
    - "events.*.name"

# LanceDB (same storage backend as main storage)
vector_search:
  path: "/app/.dbdata/vectors"       # Subdirectory of main storage
  table_name: "span_embeddings"

# DataFusion
datafusion:
  memory_limit: "512MB"
  batch_size: 8192

# Data retention
retention:
  metadata_days: 90                  # Keep summaries for 90 days
  vector_days: 90                    # Keep embeddings for 90 days
  parquet_days: 365                  # Keep parquet files for 1 year
```

### Data Retention

**Local Filesystem**: Data retention is managed by a background cleanup job in the Python backend service. Configure via `retention` settings.

**S3/Cloud Storage**: Use provider-specific lifecycle rules for automatic expiration:

```json
{
  "Rules": [
    {
      "ID": "ExpireOldSpans",
      "Status": "Enabled",
      "Filter": { "Prefix": "spans/" },
      "Expiration": { "Days": 365 }
    },
    {
      "ID": "ExpireOldVectors",
      "Status": "Enabled", 
      "Filter": { "Prefix": "vectors/" },
      "Expiration": { "Days": 90 }
    }
  ]
}
```

---

## Memory Budget

**Minimum Requirement: 1GB RAM**

| Component | Allocation | Notes |
|-----------|------------|-------|
| OS + overhead | 120MB | Standard Linux |
| Go Ingestion | 80MB | SQLite + gRPC server |
| Python Backend | 350MB | DuckDB + DataFusion + API |
| Embedding model | 150MB | all-MiniLM-L6-v2 |
| Query headroom | 300MB | For DataFusion queries |
| **Total** | **1000MB** | Comfortable fit |

---

## Latency Expectations

| Operation | Target | Notes |
|-----------|--------|-------|
| OTLP span ingestion | <5ms | Write to SQLite |
| List live spans (Go) | <20ms | SQLite indexed query |
| List historical spans (DuckDB) | <50ms | Metadata only |
| Get trace (live) | <50ms | SQLite |
| Get trace (historical) | 100-300ms | Storage Parquet fetch |
| Get span details (live) | <20ms | SQLite |
| Get span details (historical) | 50-150ms | Single file storage fetch |
| Service list | <20ms | Indexed query |
| Dashboard (pre-aggregated) | <50ms | DuckDB |
| Dashboard (custom range) | 200ms-2s | DataFusion scan |
| Semantic search | 200-500ms | LanceDB + DataFusion |
| Full analytics query | 1-30s | Depends on scope |

---

## Data Flow Timing

```
T=0s      Span arrives at Go ingestion
T=0.001s  Span written to SQLite
T=0.001s  Span queryable via gRPC API
          ─── LIVE DATA AVAILABLE ───

T=1h      Flush trigger (time-based)
T=1h+5s   Parquet file written to storage
          ─── DATA IN STORAGE ───

T=1h+35s  Indexer polls, finds new file
T=1h+40s  Span summary indexed in DuckDB
          ─── DATA IN METADATA DB ───

T=1h+95s  Embedder polls, finds new file
T=1h+120s Embeddings generated and stored
          ─── DATA SEARCHABLE VIA VECTORS ───
```

**Key Insight**: Data is queryable within milliseconds of arrival via Go SQLite. Historical indexing is eventually consistent (minutes behind) but not blocking for UX.

---

## Deployment Topologies

### Docker Compose (Self-Hosted)

The default self-hosted deployment uses local filesystem storage via a shared volume mount. Both services access the same directory for Parquet files.

```
┌─────────────────────────────────────────────────────────────┐
│                       Docker Network                         │
│                                                              │
│  ┌─────────────────────┐      ┌─────────────────────┐      │
│  │     ingestion       │      │      backend        │      │
│  │       (Go)          │      │     (Python)        │      │
│  │   :4317, :50051     │      │      :8000          │      │
│  └──────────┬──────────┘      └──────────┬──────────┘      │
│             │                            │                  │
│             └──────────┬─────────────────┘                  │
│                        │                                    │
│                        ▼                                    │
│        ┌───────────────────────────────────┐               │
│        │   /app/.dbdata (shared)           │               │
│        │   ├── spans/                      │               │
│        │   │   └── year=.../month=.../     │               │
│        │   ├── vectors/                    │               │
│        │   ├── metadata.duckdb             │               │
│        │   └── spans.db (SQLite)           │               │
│        └───────────────────────────────────┘               │
│                        │                                    │
│                        ▼                                    │
│              ${JUNJO_HOST_DB_DATA_PATH}                     │
│              (Host filesystem / Block storage)              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Environment Variables**:

| Variable | Context | Purpose | Default |
|----------|---------|---------|---------|
| `JUNJO_HOST_DB_DATA_PATH` | Host | Path on host for data storage | `./.dbdata` |
| `STORAGE_URL` | Container | Storage path inside container | `file:///app/.dbdata` |
| `INGESTION_GRPC_ADDRESS` | backend | Go ingestion service address | `ingestion:50051` |

**Volume Mount Pattern**:

```yaml
# Environment variable with fallback default
${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
```

This pattern allows users to configure the host storage location via environment variable, with a sensible default of `./.dbdata` relative to the compose file.

### Cloud Deployment (AWS/GCP/DO)

For cloud deployments, configure S3-compatible storage:

```
┌─────────────────────────────────────────────────────────────┐
│                     Container Platform                       │
│                  (ECS, Cloud Run, Kubernetes)               │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Ingestion Pods                    │   │
│  │         (StatefulSet with PVC for SQLite)           │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          Object Storage (S3 / GCS / Spaces)          │   │
│  │                                                      │   │
│  │   s3://my-bucket/spans/...                          │   │
│  │   s3://my-bucket/vectors/...                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Backend Pods                       │   │
│  │       (Deployment, DuckDB rebuilt on startup)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Cloud Storage Configuration**:

| Provider | `STORAGE_URL` |
|----------|---------------|
| AWS S3 | `s3://bucket?region=us-west-2` |
| GCS | `gs://bucket` |
| DigitalOcean Spaces | `s3://bucket?endpoint=nyc3.digitaloceanspaces.com` |
| Cloudflare R2 | `s3://bucket?endpoint={acct}.r2.cloudflarestorage.com` |

### Kubernetes (Production Scale)

```
┌─────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Ingestion StatefulSet                               │   │
│  │  - Replicas: 1-3 (sharded by service if needed)     │   │
│  │  - PVC per pod for SQLite                           │   │
│  │  - Writes to shared storage (local PVC or S3)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Storage                                 │   │
│  │  Local: ReadWriteMany PVC (NFS, EFS, etc.)          │   │
│  │  Cloud: S3 / GCS (recommended for multi-node)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Backend Deployment                                  │   │
│  │  - Replicas: 2-5 (stateless, all read same storage) │   │
│  │  - DuckDB rebuilt on startup or shared PVC          │   │
│  │  - Single indexer/embedder instance (leader elect)  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Scaling Note**: For multi-node deployments with separate VMs for ingestion and backend, S3-compatible storage is recommended over shared filesystem for reliability and simplicity.

---

## Operational Considerations

### Crash Recovery

**Go Ingestion Crash**:
- SQLite WAL mode ensures durability
- On restart, database is recovered automatically
- No data loss for committed writes

**Python Backend Crash**:
- DuckDB is rebuilt from storage on startup (or restore from backup)
- LanceDB state is in storage, unaffected
- DataFusion is stateless

**Storage Unavailable**:
- Go ingestion continues buffering to SQLite
- Flush operations fail and retry with backoff
- SQLite can grow temporarily (monitor disk space)

### Monitoring

**Key Metrics to Expose**:

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `ingestion_sqlite_row_count` | Go | >500K (flush not working) |
| `ingestion_sqlite_size_bytes` | Go | >500MB |
| `ingestion_flush_duration_seconds` | Go | >60s |
| `ingestion_flush_errors_total` | Go | Any |
| `backend_indexer_lag_seconds` | Python | >300s |
| `backend_embedder_lag_seconds` | Python | >600s |
| `backend_query_duration_seconds` | Python | p99 > 5s |
| `s3_parquet_files_total` | Python | Monitor growth |

### Backup Strategy

| Component | Backup Method | Frequency |
|-----------|---------------|-----------|
| SQLite (Go) | File copy during low traffic | Hourly |
| DuckDB (Python) | File copy or SQL dump | Daily |
| Parquet files (local) | rsync, filesystem snapshots | Daily |
| Parquet files (S3) | S3 versioning or cross-region replication | Continuous |
| LanceDB (local) | rsync with Parquet files | Daily |
| LanceDB (S3) | S3 versioning | Continuous |

**Recovery Priority**:
1. Storage data is source of truth - must be preserved
2. DuckDB can be rebuilt from storage
3. SQLite data is recent only - acceptable to lose small window

### Scaling Limits

| Scenario | Limit | Mitigation |
|----------|-------|------------|
| Spans/sec ingestion | ~100K/sec (SQLite) | Shard by service to multiple ingestion instances |
| Concurrent queries | ~50 (Python) | Add backend replicas, all read same storage |
| Storage file count | Millions | Partition by date, use filesystem walk or S3 inventory |
| Metadata DB size | ~10GB comfortable | Aggressive retention, archive old summaries |
| Vector index size | ~10M vectors | Partition by time, use IVF index |

---

## Security Considerations

### Network

- OTLP ingestion should be internal only (no public exposure)
- Backend API may be exposed with authentication
- For S3: access via IAM roles preferred over access keys

### Data

- Span attributes may contain sensitive data (user IDs, queries)
- Consider attribute filtering at ingestion
- For S3: encryption at rest (SSE-S3 or SSE-KMS)
- For local: filesystem encryption if required
- Vector embeddings may leak information - same retention as spans

### Access Control

- Multi-tenant: Filter by service_name at API layer
- Read tokens for external query access
- Write tokens separate from read

---

## Future Considerations

### Potential Enhancements

1. **Streaming ingestion to S3**: Skip SQLite for very high volume, accept higher latency
2. **Column pruning**: Store large attributes in separate column files
3. **Tiered storage**: Hot (SSD) / Cold (S3) automatic migration
4. **Query caching**: Redis layer for repeated queries
5. **Adaptive sampling**: Reduce volume while preserving signal

### Integration Points

- **Grafana**: DataFusion supports SQL, expose as data source
- **Jupyter**: Direct S3 Parquet access for analysis
- **dbt**: Transform Parquet files for downstream analytics
- **LLM Analysis**: Use LanceDB embeddings for AI-powered insights

---

## Appendix: Design Decisions

This section documents key architectural decisions and the alternatives considered.

### Decision 1: SQLite for Live Span Buffer

**Choice**: SQLite in WAL mode

**Alternatives Considered**:

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **tidwall/wal** | Fastest writes (~500K/sec), minimal memory | No query capability, requires manual in-memory indexes, index rebuild on crash | ❌ Complexity |
| **BadgerDB** | Fast LSM writes, used by Jaeger | Unpredictable memory growth (users report 2GB+ for large datasets), Jaeger explicitly recommends against production use, tuning is "black box" | ❌ Memory issues |
| **bbolt** | Low memory (mmap), B+tree range queries | Manual secondary indexes via buckets, slower writes than LSM | ❌ Manual indexes |
| **Pebble** | Better memory control than BadgerDB | Still requires manual key-prefix indexes | ❌ Manual indexes |
| **SQLite WAL** | Automatic indexes, full SQL queries, predictable memory (~5-20MB), concurrent reads, battle-tested | Single writer, ~100K writes/sec (not 500K) | ✅ Selected |

**Rationale**: Write throughput of 100K/sec is sufficient for target workloads (typical AI app: ~1-5K spans/sec). SQLite eliminates manual index maintenance and provides predictable memory behavior. BadgerDB's memory issues are well-documented in GitHub issues and Jaeger's own documentation recommends Elasticsearch for production.

---

### Decision 2: DataFusion for S3 Queries (Not DuckDB)

**Choice**: Apache DataFusion as query engine for S3 Parquet files

**Key Distinction**:
- **DuckDB** = Database (data copied INTO .duckdb file via INSERT)
- **DataFusion** = Query engine (reads files directly from storage, no ingestion step)

| Aspect | DuckDB | DataFusion |
|--------|--------|------------|
| S3 query pattern | Copy to local → query | Query directly from S3 |
| Memory at idle | Size of loaded data | Near zero |
| Data duplication | Yes (local copy) | No |
| Horizontal scaling | Complex (replication) | Simple (stateless) |

**Rationale**: DataFusion's "query-on-storage" pattern matches our architecture - S3 is the source of truth, compute is stateless. This is the same pattern used by Pydantic Logfire (Fusionfire), Trino, and Spark.

**DuckDB still used for**: Metadata database (span summaries, file registry) where data is small and query speed is critical.

---

### Decision 3: LanceDB for Vector Search (Not Qdrant)

**Choice**: LanceDB with Lance files on S3

**Alternatives Considered**:

| Aspect | Qdrant (on_disk) | LanceDB (S3) |
|--------|------------------|--------------|
| Architecture | Embedded process with local state | Query-on-storage (like DataFusion) |
| Storage | Local disk | S3-native |
| Memory at idle | ~100MB | ~30MB |
| Query latency (local) | ~5-20ms | ~20-40ms |
| Recall@10 | 95-98% (HNSW) | 88-95% (IVF-PQ) |
| Horizontal scaling | Complex (state replication) | Simple (all read S3) |

**Rationale**: LanceDB's S3-native architecture matches DataFusion's pattern - single storage backend, stateless compute. The 5-10% recall difference is acceptable for span search use cases, and can be mitigated with reranking if needed. Architectural consistency outweighs marginal recall improvement.

---

### Decision 4: Metadata Database for Span Summaries (Not Full Data)

**Choice**: DuckDB stores span summaries; full span data fetched from S3 via DataFusion

**Problem**: Storing all span data in metadata DB causes unbounded growth

**Solution**: Two-tier data model

| Tier | Storage | Contains | Size |
|------|---------|----------|------|
| Metadata (DuckDB) | Local disk | Span ID, trace ID, service, name, time, status, duration | ~100 bytes/span |
| Full data (S3 Parquet) | Object storage | Above + attributes, events, resource_attributes | ~500-2000 bytes/span |

**Rationale**: UI list views need only summary fields (fast, from DuckDB). Detail views fetch full data on-demand (acceptable latency from S3). This keeps metadata DB bounded (~1-10GB) regardless of total span volume.

---

### Decision 5: Flush Strategy (Hourly/100MB, Not Frequent Small Files)

**Choice**: Flush to Parquet when time >= 1 hour OR size >= 100MB

**Problem with frequent flushes** (e.g., every 5 seconds):
```
5 sec × 60 min × 24 hr × 365 days = 6.3 million files/year
```
- S3 LIST operations become slow and expensive
- DataFusion query planning overhead increases
- Small files = poor compression ratios

**Recommended file characteristics**:
- Target size: 50-200MB per file
- Files per day: ~24-50 (manageable)
- Row group size: 122,880 (optimal for DuckDB/DataFusion)

**Rationale**: Larger, fewer files optimize for query performance. Live data available immediately via SQLite; Parquet is for historical queries where seconds of latency is acceptable.

---

### Decision 6: Local Filesystem Default, S3 Optional

**Choice**: Local filesystem as default storage, S3-compatible storage as configurable option

**Alternatives Considered**:

| Option | Pros | Cons |
|--------|------|------|
| S3-only (MinIO for local) | Single code path, same as cloud | Extra container (+100-200MB RAM), HTTP overhead, more complexity |
| Local filesystem only | Simplest, fastest I/O | No cloud option, manual migration path |
| **Local default, S3 optional** | Simple default, cloud-ready when needed | Two backends to test |

**How we achieve single code path**:

| Language | Library | Capability |
|----------|---------|------------|
| Go | `gocloud.dev/blob` | URL-based backend selection (`file://` vs `s3://`) |
| Python | `pyarrow.fs` | Same `object_store` crate used by DataFusion/LanceDB |

Both libraries provide unified APIs - same code works for local and S3. The URL scheme determines the backend.

**Rationale**: Local filesystem is simpler and faster for self-hosted single-node deployments (the primary target). S3 adds deployment complexity (MinIO container) and HTTP overhead. Storage abstraction libraries let us support both backends without maintaining separate code paths. Users can upgrade to S3 when scaling to multi-node or cloud deployments.

---

### Decision 7: Go for Ingestion, Python for Backend

**Choice**: Polyglot architecture

| Component | Language | Rationale |
|-----------|----------|-----------|
| Ingestion | Go | Low memory footprint, excellent concurrency, mature OTLP libraries, efficient Parquet writing via Arrow |
| Backend | Python | LiteLLM integration, Pydantic AI, sentence-transformers, DataFusion bindings, rapid development |

**Alternatives Considered**:
- **All Go**: Would require reimplementing LiteLLM, embedding models, lacks mature DataFusion bindings
- **All Python**: Higher memory overhead for ingestion, GIL limits concurrency for OTLP receiver
- **Rust**: Optimal performance but slower development velocity, smaller team expertise

**Rationale**: Each language plays to its strengths. Go handles high-throughput, low-latency ingestion. Python handles AI/ML integrations and complex query orchestration. gRPC provides efficient inter-service communication.

---

## Appendix: Technology Choices Summary

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Ingestion language | Go | Low memory, high concurrency, OTLP libs |
| Live buffer | SQLite WAL | Queryable, auto-indexed, predictable memory, battle-tested |
| Storage format | Parquet | Columnar, compressed, ecosystem support |
| Storage abstraction (Go) | `gocloud.dev/blob` | URL-based backend selection, first-class S3/GCS, Google-maintained |
| Parquet writing (Go) | `apache/arrow/go` | Standard Arrow implementation, efficient encoding |
| Storage abstraction (Python) | `pyarrow.fs` | Same `object_store` as DataFusion/LanceDB, zero impedance mismatch |
| Default storage | Local filesystem | Simplest, fastest, no extra containers |
| Optional storage | S3-compatible | For cloud deployments, horizontal scaling |
| Metadata DB | DuckDB | Fast analytics, embedded, Parquet-native |
| Query engine | DataFusion | Reads Parquet directly from storage, low memory |
| Vector search | LanceDB | S3-native, embedded, growing ecosystem |
| Embeddings | sentence-transformers | Open source, local, no API costs |

---

*Document Version: 4.0*
*Last Updated: 2025*
