# ADR-009: Bounded ingestion API-key validation

## Status

Accepted

## Date

2026-07-16

## Context

Junjo Studio authenticates each OTLP trace export at the public Rust ingestion
service before accepting its spans into the segmented Arrow IPC WAL. The
ingestion service delegates the authoritative decision to the Studio backend,
which performs an indexed lookup in the application SQLite database.

The historical implementation cached successful validations in ingestion for
600 seconds. That kept repeated valid exports off the backend hot path, but a
key deleted just after validation could remain usable for ten minutes. The
initial L5 remediation removed successful-validation caching entirely. At that
proposal baseline, deletion became authoritative on the next export, but every
OTLP export waited for an ingestion-to-backend gRPC call and SQLite lookup, and
the backend client created a new gRPC channel for each validation. The
implementation governed here has now replaced that interim behavior.

Neither extreme is a suitable final default for Studio:

- a ten-minute stale-validity window is too long and was not an explicit
  security contract;
- an authoritative lookup for every export adds avoidable CPU, connection,
  scheduling, logging, and transient-memory pressure;
- Junjo targets small single-node deployments where backend queries,
  ingestion, and the frontend share a limited CPU and memory budget;
- OpenTelemetry exporters already batch spans, but sparse workloads and many
  concurrent exporters can still generate frequent export requests;
- availability failures must remain retryable and must not be confused with
  invalid credentials.

This decision concerns admission authorization only. It does not change the
OTLP client contract after admission, segmented WAL persistence, Parquet cold
storage, hot snapshots, the metadata index, or DataFusion query behavior.

The implementation and benchmark sequence is tracked in the
[Studio ingestion API-key authorization performance plan](../../../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_PERFORMANCE.md).

## Decision

Adopt a bounded, positive-only authorization cache in the ingestion service,
backed by one long-lived multiplexed Tonic channel and authoritative backend
refreshes.

The implementation defaults to a fixed 10-second TTL based on the constrained
historical, candidate-matrix, failure, and soak evidence recorded in the linked
plan. The selected values below are the accepted production contract.

### Revocation is bounded, not immediately consistent

A successful validation may be reused only until its fixed expiration time.
After expiration, ingestion must not admit another export for that key without
a successful authoritative backend validation.

The externally meaningful guarantee is:

> A deleted API key can remain accepted for no longer than the configured
> positive-validation TTL, plus ordinary scheduling tolerance and an export
> already racing with deletion.

The implementation must use expiration from the time of successful validation,
not time-to-idle expiration. Continued traffic must never extend a cached
authorization indefinitely.

The TTL must have a safe bounded default. Selecting a default longer than 30
seconds requires an explicit amendment to this ADR with performance and
security evidence. Restoring the historical 600-second default is not allowed
by this decision.

### Cache only successful validation

The cache stores only a bounded positive authorization fact. It must not cache:

- an invalid-key result;
- a backend connection or RPC failure;
- a backend database failure;
- a timeout or concurrency-saturation result.

Invalid keys therefore remain authoritative misses on every attempt. Backend
or database failures remain retryable `UNAVAILABLE` outcomes. Expired entries
must not be served stale when refresh fails.

The cache must have an explicit entry limit appropriate for a small host. The
accepted default is 1,024 entries; the capacity matrix showed that 256 entries
caused avoidable refresh churn at 300 active keys. Random invalid credentials
must not consume that capacity.

### Coalesce refreshes for the same key

Concurrent cache misses or expirations for one key must share one backend
validation. One request performs the refresh while other requests for the same
key await that result.

This singleflight behavior is part of the design, not an optional
optimization. A cache that allows every concurrent request to perform the same
refresh still creates a backend and SQLite stampede at each expiration
boundary.

The shared result is returned to current waiters, but only a successful result
is inserted into the cache.

### Reuse one multiplexed backend channel

`BackendClient` owns a long-lived Tonic `Channel`, or an equivalent cloneable
client backed by one multiplexed HTTP/2 connection. A logical client may be
cloned per request; a new transport channel must not be created for every
validation.

The channel must reconnect after backend interruption. Channel reuse does not
change authorization freshness because the backend still evaluates every
cache refresh.

### Bound cold-validation work

Cache misses for many distinct keys can bypass same-key coalescing. Actual
backend validations must therefore have an explicit global concurrency bound.
The accepted default is 8 for the one-vCPU profile. The constrained benchmark
compared bounds of 4, 8, and 16.

The system must also bound the number of decoded OTLP requests waiting for a
cold authorization result, including coalesced waiters for one key. The
accepted pending-request bound is 32. Cache hits do not consume this budget.
When either bounded path is saturated or the deadline is exceeded, ingestion
returns retryable `UNAVAILABLE`. The exporter owns retry buffering; ingestion
must protect its process memory.

The accepted backend validation deadline is two seconds for a same-host or
same-network backend. The matrix compared one-, two-, and five-second
candidates under a controlled 1.25-second backend delay.

### Preserve low-resource behavior

The selected defaults must be proven on the supported one-vCPU/1GB deployment
profile while ingestion and backend querying run together. The decision is not
complete based on an isolated SQLite microbenchmark or unconstrained developer
hardware.

The benchmark must cover:

- shared-key and distinct-key exporters;
- synchronized and staggered export timing;
- sparse and full OTLP batches;
- valid, invalid, deleted, slow-backend, and unavailable-backend cases;
- ingestion alone and ingestion during hot/cold Studio queries;
- throughput, latency, CPU, RSS, sockets, validation rate, retry behavior, WAL
  persistence latency, and query latency.

The shortest TTL that satisfies the low-resource acceptance gates should be
selected. Performance is not grounds for silently lengthening revocation
beyond the documented bound.

### Use aggregate, low-cardinality observability

Successful validation must not emit INFO logs per export or per refresh in the
steady state. Debug logging may be available for diagnosis. Production
observability should use aggregate counters and latency measurements for:

- cache hits and misses;
- coalesced waiters;
- backend validation outcomes;
- validation latency;
- saturation or timeout rejections;
- current cache entry count.

Credentials, credential prefixes, and credential-derived values must not be
metric labels.

### Keep authorization separate from telemetry storage and querying

Authorization completes before OTLP spans are converted and admitted to the
WAL. Once admitted, the existing storage flow remains authoritative:

`OTLP -> pending batch -> Arrow IPC WAL -> hot snapshot / cold Parquet`

The existing query flow also remains separate:

`REST query -> SQLite metadata selection + PrepareHotSnapshot -> DataFusion`

The positive authorization cache must not become a span cache, query cache,
or persistence dependency. The existing short `PrepareHotSnapshot` cache is a
different concern and is unaffected by this decision.

## Selected defaults

| Setting | Measured candidates | Accepted default |
| --- | --- | --- |
| Positive TTL | 5, 10, 15, 30 seconds | 10 seconds |
| Maximum positive entries | 256, 1,024 | 1,024 |
| Backend validation concurrency | 4, 8, 16 | 8 |
| Pending cold authorization requests | 16, 32, 64 | 32 |
| Backend validation deadline | 1, 2, 5 seconds | 2 seconds |

These are the active production defaults. Changing a bound remains an ordinary
evidence-backed configuration decision inside the allowed ranges. Selecting a
TTL above 30 seconds, serving stale authorization after expiry, or restoring
the historical 600-second behavior requires a new ADR.

## Alternatives considered

### No cache and authoritative validation on every export

This was the interim security remediation and remains the comparison baseline.
It provides next-export revocation, but makes backend availability and
per-export Python, SQLite, gRPC, and scheduling work part of every successful
ingestion request.

### Historical 600-second positive cache

Rejected because its revocation window is excessive, implicit, and unrelated
to a measured low-resource requirement.

### Time-to-idle expiration

Rejected because regular traffic could keep a deleted key authorized
indefinitely.

### Cache invalid and unavailable outcomes

Rejected. Negative caching delays newly created credentials, while caching
failures confuses backend availability with authoritative authorization.

### Serve expired entries during backend failure

Rejected because backend failure would silently extend the documented
revocation bound.

### Immediate backend-driven invalidation

Deferred. It can eventually support a longer fallback TTL with near-immediate
normal revocation, but it requires multi-replica delivery, retry, deletion-race,
and failure semantics. A short fixed TTL is simpler, bounded under failure, and
must be measured before adding another control-plane protocol.

### Validate credentials locally in ingestion

Rejected for the current architecture because it would duplicate or relocate
the authoritative API-key store and revocation policy. The backend remains the
authorization authority.

## Consequences

### Positive

- Repeated valid exports avoid most backend and SQLite work.
- Shared-key bursts collapse to one refresh rather than a stampede.
- A multiplexed channel removes connection churn.
- Cache and validation memory are explicitly bounded.
- Revocation has a short, explainable upper bound.
- Brief backend failures do not interrupt keys that are still inside their
  already-authorized fixed window.
- Invalid credentials and expired credentials during outages still fail
  closed with correct retry semantics.

### Negative

- Revocation is not immediately consistent.
- More concurrency and expiration behavior must be tested than in the
  no-cache interim implementation.
- Operators must understand the configured revocation bound.
- Ingestion temporarily retains bounded authorization state.
- Cache effectiveness depends on the number of active keys and exporter timing.

## Acceptance evidence

All acceptance requirements passed on 2026-07-16:

1. The 42-scenario constrained matrix covers every numeric candidate, exporter
   counts 1/10/100, shared and distinct credentials, synchronized and staggered
   timing, 1/32/128/512 spans per batch, start-to-start and after-completion
   cadence, mixed queries, and a controlled backend delay.
2. Three equal-rate historical warm-cache runs and three accepted bounded-cache
   runs each completed 5,000 exports. Median throughput was 504.28 versus
   504.31 exports/second. Median mixed-query p95 improved from 47.02 ms to
   40.68 ms.
3. The pinned no-cache/fresh-channel baseline fell to 211.98 exports/second
   with 408.31 ms export p95 and about 5,000 TCP records. Reusing one channel
   restored 500.95 exports/second and kept ingestion to at most six TCP records
   in the corresponding mixed run.
4. At a five-second after-completion exporter cadence, a five-second TTL made
   400 authoritative calls for 400 exports. Ten seconds made 200 calls, with
   zero overload retries and lower export p95, so ten seconds is the shortest
   candidate that materially reduces backend work in that representative case.
5. With 300 active distinct keys and an explicit round barrier, capacity 256
   caused 44 additional authoritative refreshes; capacity 1,024 caused none.
6. Three-run cold-burst comparisons select eight refreshes: it had the highest
   median throughput, fewest median retries, and lower median ingestion memory
   than four or sixteen. Sixteen materially worsened validation and query
   latency. The 32-request pending bound gave the best balanced query result
   without retaining the 64-request candidate's extra decoded payload budget.
7. A controlled 1.25-second backend delay failed retryably with the one-second
   deadline and succeeded with two and five seconds. Two seconds is the shortest
   candidate that tolerates that transient.
8. Paused-clock tests prove fixed expiration, non-sliding access, no stale use
   after failure, deletion at expiry, the documented in-flight deletion race,
   positive-only insertion, capacity, cancellation-safe singleflight, timeout,
   and retryable overload. One hundred simultaneous same-key misses perform one
   backend validation.
9. The real-path failure harness proves invalid results are not cached, a
   sub-deadline delay succeeds, a timeout is retryable and not cached, a warm
   entry survives a brief outage, an expired entry fails closed, and recovery
   succeeds.
10. The 60-second soak completed 6,000 exports and 1,812 authenticated queries,
    then recovered on the first validation after each of 20 endpoint restarts.
    During the restart phase ingestion RSS changed from 15.59 to 15.42 MiB,
    descriptors from 15 to 14, and established sockets from three to two. The
    extra TCP records were `TIME_WAIT`, not live-connection leaks.
11. The WAL probe observed the durable segment timestamp before acknowledgement
    within the documented 2 ms cross-clock comparison tolerance.
12. Canonical Compose, minimal, and VM/Caddy configuration, validators, public
    docs, source docs, and the comprehensive review ledger state the same
    bounds and failure semantics.

Machine-readable evidence is linked from the governing roadmap, including the
[candidate matrix](../../../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_MATRIX_2026-07-16.json),
[resource/reconnect soak](../../../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_SOAK_2026-07-16.json),
and [raw historical/current runs](../../../../docs/roadmaps/evidence/studio-ingestion-auth-2026-07-16/README.md).

## Source of truth

Active behavior lives in:

- `ingestion/src/server/auth.rs`
- `ingestion/src/backend/client.rs`
- `ingestion/src/server/trace_service.rs`
- `ingestion/src/config.rs`
- `backend/app/features/internal_auth/grpc_service.py`
- `backend/app/db_sqlite/api_keys/`

## Related

- [ADR-001: Segmented WAL architecture](../../ingestion/adr/001-segmented-wal-architecture.md)
- [ADR-002: SQLite metadata index](../../ingestion/adr/002-sqlite-metadata-index.md)
- [Studio ingestion API-key authorization performance plan](../../../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_PERFORMANCE.md)
