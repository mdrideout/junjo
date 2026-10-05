# ADR-011: Rust backend and single-origin Studio

## Status

Accepted on 2026-10-03, at the decision gate of the
[Studio backend Rust migration plan](../../../../docs/roadmaps/STUDIO_BACKEND_RUST_MIGRATION.md),
with the measured comparison recorded under "Acceptance evidence".

Amended 2026-10-04: Parquet filter pushdown is on. See "2026-10-04
amendment". Two changes to how a query reads the hot and cold tiers were
decided the same day. Ingestion ADR-002 owns them.

The Python backend remains the released backend until that plan's cutover.

## Date

2026-10-03

## Context

Studio runs three containers: a Python/FastAPI backend, a Rust ingestion
service, and an nginx container that serves the React build. The backend is the
largest memory consumer in the stack. September 2026 evidence records its peak
sampled working set at 320–351 MiB under load, against 35–51 MiB for ingestion
in the same runs. Those backend figures include file cache and native Arrow
allocations, so the interpreter's share is not isolated.

Junjo's ability to run on small, memory-constrained hosts is a product
requirement. The backend's structure also carries work that exists only
because of the language or its bindings: a connection pool in front of a
single-writer database, per-file query registration, materializing fallbacks,
and a schema defined once in models and again in generated migrations.

Serving the UI from a separate origin adds a container, CORS handling, a
same-site check for cookies, and two public URL settings that must agree.

Studio is greenfield. It has no upgrade contract for existing application
data, and intentional breaking changes are allowed when they are documented
and coordinated.

## Decision

### The backend is a Rust service with the same role

One Rust process replaces the Python backend. It keeps the same
responsibilities: the HTTP API, the internal gRPC service that ingestion calls,
metadata indexing, and queries over cold and hot span data.

The telemetry contract, the Parquet layout, the internal proto contracts, and
the hot snapshot bridge are unchanged. Ingestion is unchanged.

### One process, two listeners, one runtime

- HTTP and internal gRPC stay on separate ports so the internal port is never
  published.
- One Tokio multi-thread runtime serves both listeners and query execution.
- Metadata indexing runs on its own dedicated thread as a synchronous loop.
- The process exits non-zero if any long-lived task ends unexpectedly.

### Studio is one origin

The backend serves the existing React build as static files. This is not
server-side rendering, and the React application does not change.

- Every API route lives under `/api/v1`. `/health` stays at the root. Every
  other GET returns the application.
- The frontend calls the API with same-origin relative URLs. In development
  the Vite server proxies API requests, so the browser is same-origin in both
  modes and the backend carries no CORS handling.
- The backend no longer needs to know its own public URLs.

Root-level API routes move because the React application owns `/`, `/sign-in`,
`/sign-out`, and `/users` as pages.

### The HTTP contract is stable for the SDK

Routes that the SDK uses, every status code, and every success payload are
unchanged. Browser-facing routes move under `/api/v1`.

Every error response has one body shape with a stable code and a message. This
is the shape evaluation conflicts already use. Status 422 remains exclusive to
caller validation, as Studio ADR-007 requires.

### Each SQLite database has one writer and one reader

Each database has exactly one writer connection and one reader connection,
each on its own thread. The metadata writer belongs to the indexer thread.

- The writer connection is the write-serialization boundary that Studio
  ADR-010 requires.
- A write transaction runs to completion on the database thread. It does not
  hold SQLite's write lock while an asynchronous task is suspended.
- A fixed connection count keeps page-cache memory predictable, as ingestion
  ADR-002 requires.

### SQL files own the schema

One desired-state SQL file per database is the only schema source. There is no
ORM and no code-generated schema.

- There are no migration files while Studio has no upgrade contract.
- The application database refuses to start on a schema version mismatch. The
  metadata database is deleted and rebuilt from Parquet, because it is derived.
- When the product commits to preserving data, migrations are generated from
  the schema file's diff rather than written by hand.
- The schema file is the review surface: every schema change is a diff of that
  one file. Tests apply it to an empty database and prepare every repository
  statement against it.

This replaces the rule that migrations are generated from models and never
hand-edited. That rule guarded against models and migrations drifting apart,
which cannot happen with a single source.

### DataFusion stays, with one shared runtime

The query engine and its SQL semantics are unchanged: SQLite selects files and
DataFusion decides which spans match inside them.

One process-wide DataFusion runtime replaces the per-query runtime. The
configured spill pool therefore bounds all concurrent queries together.

### Evidence logic is pure

Payload parsing, Store reconstruction, Agent and Workflow diagnostics, and
trace evidence assembly live in a library that performs no I/O. Its behavior is
proven against the shared telemetry fixtures and the generated projections.

### Studio releases two images

The main image carries the backend binary and the built UI and is published as
`mdrideout/junjo-ai-studio-app`. Ingestion stays
`mdrideout/junjo-ai-studio-ingestion`. The `-backend` and `-frontend`
repositories are retired and left frozen at the last Python release. The
`-aio` name is reserved for a possible all-in-one image.

The frontend keeps its own dependency lock, tests, and lint. It stops being a
separately released artifact.

### Low-resource behavior decides acceptance

The migration proceeds only after a small slice is measured against the
unchanged Python backend on the supported resource profile, reporting
completed work, latency, CPU, and memory. No pass threshold is chosen in
advance; the maintainer decides from the results.

Memory limits in Compose and the deployment distributions are not changed by
this decision.

## Alternatives considered

### Keep Python and continue optimizing

The September metadata work cut backend CPU and memory substantially without
changing language. It remains possible to continue. It does not remove the
interpreter and binding floor, and each further gain requires working around
the same structure.

### One process for backend and ingestion

Rejected. Ingestion backpressure reads process memory
([ingestion ADR-001](../../ingestion/adr/001-segmented-wal-architecture.md)),
so query memory in the same process would trigger ingest rejections. Process
isolation of the acknowledgement path is also a product property.

### One Cargo workspace shared with ingestion

Rejected. It would force an Arrow upgrade onto the ingestion hot path and break
the rule that each deployable keeps its own lockfile.

### Ingestion validates API keys locally

Already rejected by Studio ADR-009.

### Another runtime or web framework

Rejected. DataFusion, Hyper, and the SQLite and session libraries require
Tokio, so another runtime would be added rather than substituted. The web
framework is a thin layer over the HTTP stack that Tonic already brings; the
backend's cost is in SQLite, DataFusion, and JSON.

### A different query engine, or none

DuckDB would add a C++ build with its own allocator and threads. Reading
Parquet directly for Studio's few fixed query shapes would give the smallest
footprint, but Studio would own filtering, deduplication, and sorting, and it
would reverse ingestion ADR-002. DataFusion is kept, and its memory floor is
measured before the full port depends on it.

### An ORM or compile-time checked SQL

Diesel and SeaORM generate schema changes from code but cannot express CHECK
constraints or indexes, which are most of this schema. `sqlx` checks queries at
compile time, but its transactions span `await` points and it cannot be linked
beside the selected SQLite binding.

### Server-side rendering

Rejected. The UI sits behind a sign-in and keeps its state in the client.
Rendering on the server would add a runtime without a payoff.

## Consequences

### Positive

- The backend's interpreter and binding overhead is removed.
- Studio runs as two containers instead of three.
- Required production settings drop from seven to three.
- CORS handling and the same-site check disappear.
- The schema has one source and every change is a visible diff.
- Concurrent queries share one memory bound.

### Negative

- This is a breaking release. Data volumes are reset, every user signs in
  again, browser-facing routes move, and the image names change.
- The backend build is slower and its dependency graph is larger.
- The backend image now depends on the frontend build.
- Studio owns SQL text and row mapping directly.
- Parity must be proven for evidence assembly, which is the largest body of
  logic in the backend.

## Acceptance evidence

The measured comparison from work package 2 is recorded in
[the measurement slice evidence](../../../../docs/roadmaps/evidence/studio-backend-rust-2026-10-03/README.md).

On the supported resource profile a slice of the Rust backend completed the
same work as the Python backend in every run:

- 42% less backend CPU while ingesting with concurrent queries, and 79% less
  in the index-completion workload;
- peak sampled backend memory of 48–100 MiB against 310–375 MiB;
- unchanged ingestion throughput, ingestion CPU, and export latency when each
  service has its own CPU quota; and
- on one shared CPU, equal ingestion when no indexing overlaps a burst, and a
  6% slowdown against 33% when it does.

The slice covers startup, both databases, sessions, API keys, the internal
gRPC service, the indexer, service discovery, and the trace query. Evidence
assembly, the remaining HTTP surface, and UI serving are not yet measured.

Build settings adopted from that evidence:

- Release builds use link-time optimization. It lowered resident memory by
  about 19 MiB and the binary from 163 MB to 91 MB.
- The system allocator is kept. `mimalloc` used about 50 MiB more memory with
  no CPU gain.
- DataFusion's runtime caches keep their upstream defaults.
- Parquet filter pushdown stayed off, because that comparison had no query
  with a filter. The 2026-10-04 amendment turns it on.

## 2026-10-04 amendment

Parquet filter pushdown is on, together with filter reordering.

The engine now applies a query's filters while it decodes a Parquet file. It
decodes the filter's columns first and decodes the remaining columns only for
the rows that match. Before this amendment it decoded every column of every
row in the row groups it read and filtered afterwards, as the Python backend
did. Reordering lets the engine run the cheaper filters first.

[The final image evidence](../../../../docs/roadmaps/evidence/studio-backend-rust-final-2026-10-04/README.md)
measured the filtered queries that the first comparison lacked. With pushdown
on, backend CPU fell by 50% for trace queries and by 57% for listing queries.
Every query returned the same rows, and memory was the same to within the
range of the runs. The maintainer decided on that evidence.

It is not a setting. The measurement-only variable that switched it is
removed.

The same day the maintainer decided two changes to how a query reads the two
tiers: a listing removes cross-tier duplicates among its newest candidates,
and a query asks ingestion again when its hot snapshot changes under it.
[Ingestion ADR-002](../../ingestion/adr/002-sqlite-metadata-index.md) owns
query bridging and records both. The internal contract with ingestion, and
ingestion itself, are unchanged by them.

## Amendments required at cutover

- [Studio ADR-006](006-studio-release-transaction.md) and
  [root ADR 0001](../../../../docs/adr/0001-junjo-platform-monorepo.md): two
  images instead of three, and the renamed main image. Made 2026-10-03.
- [Studio ADR-007](007-agent-execution-diagnostics.md): the error body and the
  validation wording. Made 2026-10-03.
- [Studio ADR-004](004-events-json-contract.md),
  [Studio ADR-009](009-bounded-ingestion-api-key-validation.md),
  [Studio ADR-010](010-evaluation-control-persistence-and-api.md), and
  [ingestion ADR-002](../../ingestion/adr/002-sqlite-metadata-index.md):
  wording and source paths that name Python, FastAPI, or Alembic. Made
  2026-10-03.
- [Root ADR 0002](../../../../docs/adr/0002-platform-licensing-and-third-party-material.md):
  which image carries which license inventory, now that the application image
  holds the backend binary and the built UI. Made 2026-10-03.

## Related

- [Studio backend Rust migration plan](../../../../docs/roadmaps/STUDIO_BACKEND_RUST_MIGRATION.md)
- [ADR-012: Studio authentication](012-studio-authentication.md)
- [Ingestion ADR-001: Segmented WAL architecture](../../ingestion/adr/001-segmented-wal-architecture.md)
- [Ingestion ADR-002: SQLite metadata index](../../ingestion/adr/002-sqlite-metadata-index.md)
