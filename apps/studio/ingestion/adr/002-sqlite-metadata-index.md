# ADR-002: SQLite Metadata Index

## Status

Accepted

## Context

The backend needs a bounded-memory way to decide which cold Parquet files to query for:

- trace lookups
- service-scoped listings
- workflow-oriented queries
- LLM-oriented queries

The old architectural failure mode was per-span indexing. That shape scales with span count, not with the actual query problem we need to solve, and it does not fit the repo's small-host target.

The strategic deployment constraint here is durable:

- Junjo is intended to run on small machines
- ingestion, backend, and frontend all share that memory budget
- metadata selection cannot scale linearly with total span count

The end-state metadata layer therefore must answer "which files should DataFusion query?" while staying bounded and rebuildable.

There is also an unavoidable visibility gap between:

- ingestion flushing a cold Parquet file
- backend metadata indexing that file

The query path must remain correct during that gap.

## Decision

Use a separate SQLite metadata database with per-file and per-trace indexing rather than per-span indexing.

### End-State Strategy

The metadata database exists only to narrow the cold query set.

It is responsible for:

- tracking cold Parquet files and their time bounds
- mapping traces to file ids
- mapping services to file ids
- recording workflow-relevant and LLM-relevant query hints
- helping the backend avoid scanning all cold Parquet files

It is not responsible for:

- storing or serving full span payloads
- replacing DataFusion
- becoming a second analytical query engine

The strategic end state is:

- SQLite answers "which files should we open?"
- DataFusion answers "what spans match inside those files?"

### Why Per-Trace And Per-File Instead Of Per-Span

Per-span indexing stores far more information than the current query model requires.

The architectural observation is:

- trace lookups need trace-to-file mapping
- service listings need service-to-file mapping
- workflow and LLM queries need coarse semantic narrowing
- the backend already reads whole traces or bounded cold file sets and applies final filters with DataFusion

We do not need a primary architectural guarantee of "span_id -> file" to support the current product behavior.

So the chosen shape is:

- coarse enough to stay bounded
- rich enough to narrow the query set meaningfully
- rebuildable from cold Parquet if needed

### Why SQLite

SQLite is the right end-state metadata store here because it matches the problem shape:

- local, embedded, and operationally simple
- bounded and predictable on small hosts when concurrency is controlled
- sufficient for indexed key lookups and file-selection queries
- already a familiar dependency in the stack

More complex metadata systems would add operational weight without solving the core problem better for a single-node local-disk deployment.

### Query Bridging Strategy

The metadata index only covers cold files that have already been indexed.

To close the flush-to-index gap, the end-state query path is:

1. backend asks ingestion for `PrepareHotSnapshot`
2. ingestion returns:
   - a hot snapshot path for unflushed WAL data
   - `recent_cold_paths` for newly flushed cold files not yet indexed
3. backend selects indexed cold files from SQLite
4. backend augments those file lists with bounded `recent_cold_paths`
5. DataFusion queries cold plus hot together

This bridge is part of the architecture, not a temporary workaround.

## Guardrails

These are part of the decision and should not regress.

### Distinct Cold-Tier Service Discovery Comes From SQLite

The cold-tier service list should come from the metadata index, not from scanning all cold Parquet files.

The backend may still union in:

- recent cold files that are not indexed yet
- the hot snapshot

But broad cold scans are a regression against the purpose of the metadata layer.

### Service-Scoped Cold File Registration Must Stay Bounded

Service queries must not register an unbounded cold working set into DataFusion.

The strategic rule is:

- SQLite narrows the candidate file set
- backend applies an explicit bound for service-scoped reads

This keeps query memory proportional to the request, not to total cold storage size.

### Filesystem Reconciliation Must Use The Same Scan Rules As The Indexer

Startup sync and background indexing must agree on what counts as an indexable cold Parquet file.

That includes scan behavior such as:

- recursive partition discovery
- skipping ephemeral `tmp/` files and directories

If those rules drift apart, reconciliation can delete valid rows or miss real files.

### Indexer Concurrency Must Stay Bounded

SQLite page-cache usage grows with connection and worker count.

The architectural rule is not "use exactly one worker forever"; it is "indexing concurrency must remain intentionally bounded so metadata memory stays predictable."

### Empty `snapshot_path` Means No HOT Tier

An empty snapshot path from `PrepareHotSnapshot` means there is no hot file to read.

The backend must interpret that as "query cold plus recent-cold only," not as a recoverable path error.

### Metadata Is Rebuildable, Not Canonical

The metadata database is a derived index over cold Parquet files.

That means:

- it can be rebuilt
- corruption or drift should be fixed by regeneration/reconciliation
- the canonical cold data remains the Parquet files, not SQLite rows

Implementation defaults, table details, and historical rollout steps are not owned by this ADR. They live in code and git history.

## Alternatives Considered

### Keep Per-Span Metadata

Rejected because memory scales with total spans rather than the coarse-grained lookup problem we actually need to solve.

### Pure In-Memory Metadata

Rejected as the primary strategy because it makes memory growth less predictable as datasets scale.

### More Complex Catalog Or KV Systems

Rejected because they add more operational and build complexity than the single-node local-disk architecture needs.

### Full Cold Scans With No Metadata Layer

Rejected because the backend would repeatedly pay query-time cost to rediscover file relevance instead of using a bounded metadata index.

## Consequences

### Positive

- Metadata memory usage is bounded relative to files, traces, and coarse semantic mappings rather than raw span count.
- Cold-tier file selection remains fast on small hosts.
- The metadata layer is rebuildable from cold storage.
- Ingestion remains decoupled from backend availability.
- Very recent traces remain queryable even during the flush-to-index gap.

### Negative

- The system owns a second SQLite database.
- Correctness depends on keeping indexer scan rules, reconciliation rules, and backend query logic aligned.
- Query code must reason about three cold-related states:
  - indexed cold files
  - recent cold files not yet indexed
  - optional hot snapshot data

## Source Of Truth

The active implementation lives in:

- `backend/app/db_sqlite/metadata/`
- `backend/app/features/parquet_indexer/`
- `backend/app/features/otel_spans/`
- `backend/app/features/span_ingestion/`
- `ingestion/src/recent_cold_files.rs`
- `proto/ingestion.proto`

## Related

- `ingestion/adr/001-segmented-wal-architecture.md`
