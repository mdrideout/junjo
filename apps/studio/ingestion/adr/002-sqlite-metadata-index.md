# ADR-002: SQLite Metadata Index

Amended 2026-10-03 by
[Studio ADR-011](../../docs/adr/011-rust-backend-and-single-origin-studio.md).
The backend that owns this index is now a Rust service, so "Source Of Truth"
names its Rust modules and schema file instead of the Python packages they
replaced. The decision and its guardrails are unchanged.

Amended 2026-10-04 on the maintainer's decision: how a listing removes a span
that sits in both tiers, what the backend does when the hot snapshot changes
under a query, how the LLM listing covers files the index does not hold
yet, and when a span query asks ingestion. See "2026-10-04 amendment".

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

## 2026-10-04 amendment

Three changes were measured with the real frontend and the real SDK while
ingestion processed spans, and the maintainer decided on those results. They
are recorded in
[the final image evidence](../../../../docs/roadmaps/evidence/studio-backend-rust-final-2026-10-04/README.md)
under "Real-world runs", "The adopted build", and "The default Traces view".
The query bridging strategy above is otherwise unchanged: every query asks
ingestion, reads the hot snapshot, the recent cold files, and the indexed
cold files together, and the cold copy of a span wins.

### A listing removes duplicates among its newest candidates

A span can be in the hot snapshot and in a cold file at once only briefly.
Ingestion reuses a snapshot for about a second, so a query can be handed a
snapshot from just before a flush beside the cold file that flush wrote.

A listing wants its newest page. It takes the newest page of each tier and
removes duplicates among those candidates, not among every span that matches.
The newest page of the two tiers together is always among them, so the page
is the same and the cold copy still wins. A query with no page size, such as
one trace, still removes duplicates among everything it returns.

Before this amendment a listing numbered every matching span of every file it
read whenever a hot snapshot existed, which on a live deployment is nearly
always. Its cost followed the number of spans that matched the listing and
not the size of the page. Where every span of a service was a root span, a
Traces listing cost about a second of backend CPU where the newest page costs
milliseconds, two concurrent listings filled the query memory pool, and the
busy backend slowed its answer to ingestion's API key validation. Where one
span in 32 was a root span the same listing cost far less, and the change
gained less. The evidence reports both.

One consequence is accepted. If the same span is stored twice in one tier,
that tier offers that many fewer distinct candidates, so the oldest end of a
page can lack those spans or hold older ones in their place. A listing over
both tiers still returns no span twice. A listing over one tier has never
removed duplicates and still does not.

### The backend asks again when the hot snapshot changes under a query

Ingestion writes the hot snapshot to one path, replaces it for the first
request after its reuse period, and removes it when its log is empty. The
backend runs queries concurrently, so one query can still be reading the
snapshot when another request has it replaced.

- A query that fails after ingestion replaced or removed the snapshot it was
  handed asks ingestion again and runs once more over what ingestion names
  then. That answer names the cold file any flushed spans went to, so the
  second run reads current data.
- A snapshot that ingestion named and that is gone when the query looks is
  handled the same way. It is not left out of the query, which would answer
  without the newest spans. This is not the empty snapshot path of the
  guardrail above: that still means there is no hot tier.
- A query that ran out of memory is not run again.
- This does not make ingestion build snapshots more often. The second request
  normally falls inside the reuse period of the snapshot that replaced the
  first.

The backend does not cache what ingestion answers, and it does not hold or
copy the snapshot file. A query whose second run also meets a new snapshot
fails. Keeping queries short keeps that from happening, which is why these
two parts of the amendment were adopted together.

### The LLM listing reads what the index does not hold yet

The Traces page opens on the traces that have an LLM span. The index knows
that a trace has one only once the span's file is indexed. The bridge above
closes the flush-to-index gap for reading spans. It did not close it for this
filter: the listing asked the index and the hot snapshot, and a file that was
flushed but not yet indexed was covered by neither. Its traces left the
default view at the flush and came back when the indexer reached the file.

The listing now covers that file.

- It takes the newest root spans of the service, as before.
- It asks ingestion again. It then asks the index which of the recent cold
  files it does not hold, and after that which of the candidate traces it
  knows to have an LLM span. In that order a file that is indexed between
  the two lookups is covered by both. In the other order it could be covered
  by neither.
- It reads the hot snapshot and those unindexed files once, for the
  candidates the index did not resolve. The service, the trace identifiers,
  and a start time are filters applied while Parquet is decoded, so only
  those candidates' spans are decoded.
- The start time is that of the oldest of those candidates' root spans. A
  span of a trace does not start before the trace's root span.

Asking ingestion again is deliberate. A flush between the listing's two
reads moves unflushed spans into a file the first answer did not name, and a
rebuilt snapshot no longer holds them. The second answer names that file.
Without the second request the same read left about a tenth of default views
short at four times the standard load. With it none was short at either load.

The change has a measured cost. The maintainer chose it on the prototype's
runs, which put that cost higher than the tree's own runs then did. On the
tree's build a backend that was spending its whole CPU quota completed
about 6% fewer page loads than the build before it, and the default view took
about 90 ms longer at the median. A span was readable about a tenth of a
second later at the median. Ingestion's CPU was the same. A second request
makes ingestion build a snapshot only when it arrives after the reuse period,
and under load another request would have caused that build anyway. How
often ingestion built a snapshot was not counted.

These rules go with it.

- No other query asks ingestion twice. Doing so is work for ingestion and
  needs its own measurement and decision.
- The index is asked about the recent cold files one by one, on their unique
  path. Cold storage is not scanned, and no indexed file is read for this
  filter.
- A trace with more than one root span, or with spans whose clocks disagree,
  can have an LLM span that starts before the oldest unresolved root span.
  Such a span is found once its file is indexed, as before.

Alternatives that were considered:

- The same read without asking ingestion again. Measured: no default view
  short at the standard load and about a tenth short at four times that
  load, for a smaller cost.
- Having the indexer take a new file when a query reports it, instead of at
  its next cycle. Not measured. It shortens the gap without closing it, and
  it moves indexing into the moments when ingestion is busiest.
- Classifying spans in ingestion at flush time. Rejected: it gives the
  classification rule a second owner and adds work to the ingest path.

### The index is read first and ingestion is asked last

The bridging steps above list the request to ingestion first. A span query
now selects its indexed files first and asks ingestion last, so the answer is
as new as it can be when the files are opened. Nothing else about the steps
changes.

The reason is a window both backends have always had. If ingestion flushes
and rebuilds its snapshot after it answered and before the backend reads,
the query reads a snapshot that no longer holds the flushed spans and was
not told of the file that does. In the real-world runs a trace that the list
had just shown answered 404 on its own page, once in 7,410 loads.

Asking last narrows that window to the time between the answer and the read.
One more rule covers what is left of it for the query where it shows: a
trace or span query that finds nothing, and whose snapshot was replaced or
removed while it ran, asks ingestion again and runs once more. A listing is
not run again. It cannot tell that spans are missing.

## 2026-10-05 amendment

### The Agent listing reads a page at a time

The Agent listing returned one page and read a service's whole history for
it. It opened every indexed file that held Agent spans of the service, loaded
and sorted every one of those spans, built a summary of each, and applied the
caller's filters last. It was the one service-scoped read that the guardrail
"Service-Scoped Cold File Registration Must Stay Bounded" did not cover.
Measured with the real frontend while spans arrived, the page took about
0.9 s over 18 cold files and about 2.5 s over 72, and requests failed when
the sort ran out of memory. The numbers before and after are in
[the final image evidence](../../../../docs/roadmaps/evidence/studio-backend-rust-final-2026-10-04/README.md)
under "The two pages that read a service's history" and "The Agent listing a
page at a time".

The listing now walks the service's Agent spans from the newest, a page at a
time, and stops when it has enough summaries that pass the filters.

- **Order.** Newest first by start time. Spans that start at the same
  instant are ordered by trace and span identifier, so a place in the listing
  is exact and the next page starts after it.
- **One page.** A page asks for the newest Agent spans after a place, sorted
  and cut to the page size inside the query.
- **Filters.** The caller's start and end time bounds are part of the query.
  So are the agent, structure, version, and outcome filters, as text the
  stored span must contain, so a page holds spans that can pass them. The
  assembled summary still decides exactly which spans pass.
- **Files.** The index already records each file's time bounds per service.
  A page reads the indexed Agent files that reach across its place and the
  next 20 below it, the bound the other service listings use. The first file
  it leaves out ends at some time. Spans that started at or before that time
  could also be in files the page did not read, so the page stops above it
  and the next page continues from there.
- **The unindexed spans.** Every page is an ordinary query: it asks ingestion
  and reads the hot snapshot and the recent cold files, as before.

These consequences are accepted.

- A listing that no stored span passes reads the service's whole history, a
  group of files at a time. It costs about one read of that history and does
  not hold it in memory.
- A listing that needs more than one page asks ingestion once per page.
- An Agent span whose evidence cannot be read fails a listing only when the
  walk reaches it. Before, one such span anywhere in a service's history
  failed every listing of that service.
- A span stored twice in one tier is listed twice whether or not a hot
  snapshot exists. The walk reads a short page as the end of the files it
  read, so a page must not come back short because copies were removed. The
  cold copy of a span still replaces its hot copy.
- A file's bounds are its earliest start and its latest end. A span stored
  with an end before its start can therefore be left out.

## Source Of Truth

The active implementation lives in:

- `backend/schema/metadata.sql`
- `backend/server/src/db/metadata.rs`
- `backend/server/src/features/parquet_indexer/`
- `backend/server/src/features/otel_spans/`
- `backend/server/src/features/span_ingestion.rs`
- `ingestion/src/recent_cold_files.rs`
- `proto/ingestion.proto`

## Related

- `ingestion/adr/001-segmented-wal-architecture.md`
