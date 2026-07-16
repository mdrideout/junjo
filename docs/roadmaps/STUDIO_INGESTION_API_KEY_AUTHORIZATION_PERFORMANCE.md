# Studio ingestion API-key authorization performance plan

- Status: Complete; bounded cache, singleflight, reusable transport, selected
  defaults, constrained evidence, and ADR acceptance are complete
- Date: 2026-07-16
- Owners: Junjo Studio ingestion and backend
- Governing decision: [Studio ADR-009: Bounded ingestion API-key validation](../../apps/studio/docs/adr/009-bounded-ingestion-api-key-validation.md)

## Purpose

Resolve L5 as an explicit security, availability, latency, throughput, and
memory decision for Junjo Studio's small-host target.

The historical ingestion service cached successful API-key validations for ten
minutes. The first remediation removed the cache so deletion takes effect on
the next OTLP export. That closes the stale-key window but makes every export
await backend gRPC and SQLite work. It also amplifies the existing behavior of
creating a new backend gRPC channel for each validation.

This plan replaces both extremes with measured, bounded behavior:

- one reusable multiplexed Tonic channel;
- a short fixed-TTL, positive-only cache;
- one coalesced refresh for concurrent requests using the same key;
- bounded cold-validation concurrency and a short deadline;
- retryable failure semantics;
- aggregate observability;
- defaults selected on the one-vCPU/1GB profile.

The plan is intentionally limited to L5. The remaining findings from the
comprehensive review are separate work and must not be mixed into this
changeset or its performance conclusions.

## Current and historical baselines

### Historical committed behavior

- successful validations cached for 600 seconds;
- cache capacity 10,000 keys;
- invalid results not cached;
- each cache miss created a new backend gRPC channel;
- concurrent misses for the same key were not deliberately coalesced;
- a deleted key could remain accepted for up to ten minutes.

### Interim no-cache baseline

- no successful-validation cache;
- every OTLP export calls the backend;
- each validation creates a new backend gRPC channel;
- backend performs an indexed `api_keys.key` SQLite lookup;
- backend/database failures return retryable `UNAVAILABLE`;
- deletion is authoritative on the next export;
- persistence and hot/cold querying are unchanged.

### Active bounded implementation

- successful validation is reused for a fixed, non-sliding 10-second window;
- the cache retains at most 1,024 positive entries and never stores invalid or
  unavailable outcomes;
- simultaneous same-key misses share one cancellation-safe refresh;
- one long-lived reconnecting Tonic channel carries authoritative refreshes;
- at most eight refreshes and 32 decoded cold requests are in flight;
- refreshes have a two-second deadline, and saturation, timeout, transport, and
  database failures return retryable `UNAVAILABLE`;
- cache hits admit directly into the unchanged OTLP-to-WAL path;
- deletion becomes authoritative after the current fixed positive window,
  bounded by 10 seconds plus scheduling tolerance and an in-flight race;
- persistence and hot/cold querying remain unchanged.

### Directional evidence already collected

A local loopback harness using the real backend servicer and indexed SQLite
repository measured:

| Operation | Mean | p95 |
| --- | ---: | ---: |
| Direct indexed SQLite lookup | 0.442 ms | 0.549 ms |
| Sequential gRPC with a reused channel | 0.743 ms | 0.909 ms |
| Sequential gRPC with a fresh channel | 1.218 ms | 1.438 ms |
| 100 concurrent fresh-channel validations | 50.2 ms | 76.4 ms |

The concurrent run completed in 78.5 ms wall time, about 1,274 validations per
second. These figures explain the mechanism but are not capacity evidence:
they exclude Docker networking, Rust OTLP decoding, realistic payloads,
sustained RSS/CPU, WAL work, mixed hot/cold queries, and exporter retry queues.

## Scope lock

### In scope

- ingestion's authorization cache and refresh coordination;
- ingestion-to-backend channel lifecycle;
- validation concurrency, deadlines, and retryable overload;
- backend validation logging and low-cardinality metrics;
- API-key revocation-bound documentation;
- constrained performance, memory, outage, and mixed-workload validation;
- configuration propagation through canonical Studio deployments.

### Out of scope

- OTLP span schema or telemetry-contract changes;
- Arrow IPC WAL, Parquet, hot snapshot, recent-cold, metadata-index, or
  DataFusion redesign;
- browser or REST query behavior;
- distributed credential stores;
- immediate invalidation RPCs in the first implementation;
- unrelated comprehensive-review findings;
- compatibility fallbacks for the historical 600-second behavior.

## Target interaction

```text
OTLP Export(batch)
  -> ingestion RSS backpressure check
  -> positive authorization cache
       -> hit: admit immediately
       -> miss/expired:
            -> join same-key refresh if one exists
            -> otherwise acquire bounded validation permit
            -> reuse long-lived backend channel
            -> backend indexed SQLite lookup
                 -> valid: cache until fixed expiry; admit
                 -> invalid: do not cache; UNAUTHENTICATED
                 -> unavailable: do not cache; UNAVAILABLE
  -> convert spans
  -> pending batch
  -> Arrow IPC WAL
  -> hot snapshot / cold Parquet
```

The query path remains:

```text
Browser
  -> backend REST
  -> metadata.db selects bounded cold files
  -> PrepareHotSnapshot
  -> DataFusion hot + cold query
  -> deduplicated response
```

The two SQLite roles remain separate: `junjo.db` owns users and API keys;
`metadata.db` narrows cold Parquet query files.

## Decisions already made

These constraints should be accepted before implementation begins:

1. A bounded revocation delay is acceptable; next-export consistency is not a
   permanent requirement.
2. The cache uses fixed expiration from successful validation, never sliding
   or time-to-idle expiration.
3. Only successful validations are cached.
4. Invalid, timeout, saturation, transport, and database-failure results are
   never cached.
5. Expired authorizations are never served stale during backend failure.
6. Same-key refreshes are coalesced.
7. Backend transport is reused and multiplexed.
8. Cold-validation work and cache capacity are explicitly bounded.
9. Overload and backend failure remain retryable `UNAVAILABLE`.
10. The shortest TTL satisfying the constrained performance gates wins.
11. No default over 30 seconds may be selected without amending ADR-009.
12. The historical 600-second default will not be restored.

## Accepted defaults

| Decision | Measured candidates | Accepted value | Selection result |
| --- | --- | --- | --- |
| Positive TTL | 5, 10, 15, 30 seconds | 10 seconds | Five seconds performed one lookup per export at a five-second after-completion cadence; ten seconds halved validation work without a 15/30-second revocation window |
| Maximum positive entries | 256, 1,024 | 1,024 | Capacity 256 revalidated 44 of 300 active keys on the second barriered round; 1,024 avoided churn |
| Validation concurrency | 4, 8, 16 | 8 | Best three-run median throughput and retry count without the latency harm at 16 |
| Pending cold authorization requests | 16, 32, 64 | 32 | Best balanced mixed-query result without retaining 64 decoded requests |
| Validation deadline | 1, 2, 5 seconds | 2 seconds | One second failed retryably under a controlled 1.25-second delay; two and five succeeded |
| Cache implementation | Moka future cache or simpler bounded equivalent | Explicit bounded cache | Fixed TTL, positive-only insertion, cancellation-safe singleflight, and capacity are explicit and focused-testable |

## Implementation progress

- [x] Reuse one lazy, reconnecting, multiplexed Tonic channel.
- [x] Implement a fixed-TTL, positive-only, explicitly bounded cache.
- [x] Coalesce same-key refreshes and keep the refresh alive if its initiating
  request is cancelled.
- [x] Bound backend refreshes and all decoded OTLP requests waiting for cold
  authorization.
- [x] Preserve invalid versus retryable-unavailable semantics without caching
  either outcome.
- [x] Add aggregate low-cardinality authorization interval metrics and remove
  steady-state per-validation INFO logging.
- [x] Propagate defaults and failure semantics through canonical Compose,
  deployment distributions, validators, examples, and public documentation.
- [x] Add focused expiration, coalescing, cancellation, capacity, saturation,
  outage, and reconnect tests.
- [x] Add a repository-owned constrained real-path benchmark and record the
  initial shared-key burst and paced comparisons.
- [x] Add exact external arrival-rate pacing, shared/distinct key topology,
  synchronized/staggered timing, and reproducible jittered exporter retries.
- [x] Add delayed and unavailable backend controls, restart/resource soak,
  descriptor/socket/thread counts, and WAL durability-lag measurement.
- [x] Complete historical warm-cache, fresh-channel, candidate-capacity,
  concurrency, deadline, batch-size, timing, cadence, and query-load evidence.
- [x] Review the full evidence and accept ADR-009 with the selected defaults.

## Work packages

### 0. Accept the architectural constraints

- Review ADR-009 with security, ingestion, and backend ownership in mind.
- Confirm that bounded revocation, rather than next-export revocation, is the
  intended product contract.
- Confirm the 30-second maximum without a new ADR amendment.
- Keep ADR-009 Proposed at this stage because numeric defaults still require evidence.

Exit criteria:

- the qualitative constraints above are agreed;
- no implementation starts by restoring the historical cache unchanged;
- benchmark ownership and the one-vCPU/1GB target are explicit.

### 1. Create a reproducible constrained benchmark harness

Build a repository-owned harness that exercises the public OTLP endpoint and
real backend auth service. It must not call the repository's test functions as
a substitute for workload generation.

The harness must:

- run against the canonical Compose topology;
- apply the one-vCPU/1GB setup profile and existing container memory limits;
- generate deterministic OTLP batches with configurable span count, key count,
  exporter count, cadence, and synchronization;
- run query traffic through representative observability endpoints;
- delete a warmed key and measure its final accepted export;
- delay, stop, and restart the backend;
- capture container CPU/RSS, process sockets/file descriptors, response codes,
  latency distributions, backend validation counts, WAL persistence lag, and
  query latency;
- produce machine-readable results plus a concise comparison table;
- use synthetic credentials and leave no persistent runtime data behind.

The harness must distinguish export requests per second from spans per second.
Authorization happens per OTLP export batch, not per span.

Exit criteria:

- repeated runs on the target profile are comparable;
- baseline results can be reproduced without source edits;
- metrics identify channel churn, backend validations, cache outcomes, and
  exporter retries separately.

### 2. Record three implementation baselines

Measure, without conflating changes:

1. historical 600-second cache with fresh channels;
2. current no-cache implementation with fresh channels;
3. no cache with one reused channel.

This sequence isolates the value of channel reuse from the value of caching.
The historical build is benchmark evidence only and must not become the final
working-tree implementation.

Exit criteria:

- each baseline has ingest-only and mixed-query results;
- CPU, RSS, sockets, validation rate, export latency, and spans/second are
  captured;
- backend restart behavior is recorded for the reusable channel.

### 3. Implement reusable backend transport

- Construct one long-lived Tonic `Channel` when `BackendClient` is created.
- Clone the channel-backed logical client per validation rather than locking a
  single mutable client across the RPC.
- Preserve the authenticated internal workload-token metadata on every call.
- Configure one explicit per-RPC deadline.
- Prove automatic reconnect after backend restart.
- Prove repeated restarts do not leak sockets, tasks, or memory.
- Move successful per-validation backend logs from INFO to debug or aggregate
  them.

This work is independently useful and should land before cache policy so its
effect can be measured separately.

Exit criteria:

- one steady backend connection serves repeated validations;
- invalid and unavailable distinctions remain unchanged;
- reconnect and cleanup tests pass;
- the no-cache reusable-channel baseline is recorded.

### 4. Implement bounded positive caching and singleflight

- Add a fixed-TTL positive cache with explicit capacity.
- Key coalescing by the same credential identity so one initializer performs
  the backend refresh.
- Cache only the `valid` outcome.
- Return invalid and unavailable outcomes to current waiters without insertion.
- Do not extend entry expiration on access.
- Do not serve an expired entry if refresh times out or fails.
- Bound simultaneous backend initializers globally.
- Bound all decoded OTLP requests waiting for a cold result, including
  same-key coalesced waiters; cache hits bypass this budget.
- Return retryable `UNAVAILABLE` rather than queueing unbounded decoded OTLP
  requests when the validation path is saturated.
- Keep the cache independent from WAL and query state.

Required focused tests:

- positive hit performs no second backend call;
- fixed expiration triggers one new backend call;
- frequent access does not extend expiration;
- 100 simultaneous same-key misses perform exactly one backend call;
- simultaneous different-key misses respect the global concurrency limit;
- invalid results are not cached;
- backend failures and timeouts are not cached;
- an expired positive entry is not served during failure;
- cache capacity is bounded and eviction remains correct;
- key deletion is observed no later than TTL plus test tolerance;
- an in-flight deletion race has an explicit allowed outcome;
- backend restart works before and after cache expiry.

Exit criteria:

- all behavioral tests pass under Tokio's paused clock where applicable;
- no test uses real sleeps to prove TTL correctness;
- cache-hit and coalescing counters reconcile with backend call counts.

### 5. Run the selection matrix

Use controlled one-factor comparisons for each numeric candidate plus the
high-risk interactions below. Do not construct a full Cartesian product: it
would repeat unrelated values thousands of times, obscure causal selection,
and spend most runs re-proving identical behavior. Every dimension must appear
in the accepted matrix, and interactions that change cache semantics (key
topology, cadence/TTL, synchronization/concurrency, capacity/key count, and
deadline/backend delay) must be crossed explicitly:

- exporters: 1, 10, 100;
- key topology: one shared key, one key per exporter;
- timing: synchronized and staggered;
- spans per export: 1, 32, 128, 512;
- backend state: healthy, delayed, unavailable, restarted;
- credential state: valid, invalid, warmed then deleted;
- query load: none and representative concurrent hot/cold reads.

Primary measurements:

- OTLP exports/second and spans/second;
- OTLP acknowledgement p50, p95, and p99;
- ingestion and backend CPU and RSS;
- open sockets and file descriptors;
- backend validations/second;
- cache hit, miss, and coalesced-waiter counts;
- validation p50, p95, and p99;
- exporter retries and dropped batches;
- WAL admission-to-durable-segment delay;
- REST query p50, p95, and p99;
- observed revocation delay.

### 6. Apply acceptance gates and select defaults

The final candidate must satisfy all of these:

#### Security and correctness

- observed revocation never exceeds the configured fixed TTL plus a documented
  small scheduling tolerance;
- access does not refresh TTL;
- no stale entry is served after expiration;
- invalid and failure results are not cached;
- failures remain retryable `UNAVAILABLE`;
- same-key refresh performs one authoritative lookup.

#### Low-resource safety

- no monotonic RSS, task, connection, socket, or file-descriptor growth;
- ingestion stays below its configured RSS backpressure threshold during the
  sustained healthy workload;
- backend delay or outage cannot create an unbounded queue of decoded exports;
- cache memory remains bounded at configured capacity;
- mixed query and ingestion workloads complete without OOM or container
  restart on the one-vCPU/1GB profile.

#### Performance

- cached steady-state throughput is within 5% of the historical warm-cache
  baseline or better;
- channel reuse is measurably better than fresh-channel no-cache behavior in
  CPU, sockets, or latency and introduces no material regression elsewhere;
- shared-key refresh validation rate is approximately one backend lookup per
  active key per TTL, not one per exporter;
- mixed-query p95 latency regresses by no more than 10% relative to the
  historical warm-cache baseline at the same ingest workload;
- the selected candidate materially reduces backend validation work relative
  to the no-cache baseline.

If no TTL at or below 30 seconds passes, stop and revisit the architecture. Do
not silently extend the revocation window. The next review should consider
best-effort authenticated invalidation with a bounded fallback TTL.

### 7. Accept the ADR and synchronize configuration

- Record the selected numeric defaults and benchmark evidence in ADR-009.
- Change ADR-009 from Proposed to Accepted only after the evidence is reviewed.
- Add explicit ingestion configuration for TTL, capacity, validation
  concurrency, and deadline.
- Propagate safe defaults and explanations through:
  - Studio `.env.example`;
  - minimal deployment `.env.example`;
  - VM/Caddy deployment `.env.example`;
  - canonical Compose files where required;
  - setup profiles and their validators;
  - ingestion README and public Studio operations documentation.
- State the revocation guarantee and backend-outage behavior in operator-facing
  language.
- Update the comprehensive review ledger with the accepted architecture and
  final validation evidence.

Exit criteria:

- canonical deployments render with the selected defaults;
- config validators reject unsafe or nonsensical values;
- deployment mirrors remain generated from canonical sources;
- ADR, code, tests, and operator documentation state the same guarantee.

## Validation routing

At implementation time run, at minimum:

- `cargo test --locked` from `apps/studio/ingestion`;
- backend internal-auth unit, integration, concurrency, DB-failure, and real
  gRPC suites;
- `apps/studio/run-all-tests.sh`;
- canonical Compose rendering and deployment validators;
- the constrained benchmark matrix;
- backend restart/reconnect and resource-leak soak tests;
- mixed hot/cold query and ingestion checks;
- `git diff --check` and documentation link validation.

Changing shared internal protobufs is not planned. If implementation requires
one, add proto generation/staleness validation and update ADR-009 before
proceeding.

## Evidence record

Append benchmark runs here or link immutable repository-owned result artifacts.
Each accepted run must record:

- commit and working-tree state;
- host architecture and operating system;
- container CPU and memory constraints;
- exact workload parameters;
- exact cache and transport settings;
- summary metrics and raw-result location;
- pass/fail against each acceptance gate;
- observed anomalies and rerun disposition.

Initial constrained evidence is stored in
[`STUDIO_INGESTION_API_KEY_AUTHORIZATION_EVIDENCE_2026-07-16.json`](STUDIO_INGESTION_API_KEY_AUTHORIZATION_EVIDENCE_2026-07-16.json).
It compares no-cache, 10-second, and 15-second shared-key workloads against the
real Compose OTLP, backend authorization, WAL, and authenticated REST query
paths under 0.5 CPU and 450 MiB for backend plus 0.5 CPU and 350 MiB for
ingestion.

The initial burst comparison completed all 10,000 requested exports in every
accepted run. Relative to no cache, the 10-second candidate increased
completed export throughput from 2,134 to 3,981 exports/second, reduced export
p95 from 155.7 ms to 41.1 ms, and reduced retryable saturation attempts from
1,885 to 68. Peak ingestion memory remained small (23.89 MiB without cache,
21.69 MiB with the 10-second cache); backend memory was essentially unchanged.
The original harness measured the first rejection response at 10.003 seconds
for the 10-second candidate and 15.028 seconds for the 15-second candidate. A
later harness revision records last successful admission separately because a
rejection response also includes the post-expiry authoritative lookup.

A second, paced comparison reduced offered pressure. The 10-second candidate
still reduced export p95 from 88.0 ms to 34.6 ms and retryable saturation
attempts from 1,021 to 68, with 1.98 MiB more peak ingestion memory. Its query
p95 was 62.6 ms versus 55.7 ms, but it also completed 11.8% more exports per
second because that first harness sleeps after each completed request rather
than holding an exact external arrival rate. That run therefore does not close
the equal-offered-rate or historical-warm-cache query gate.

The start-to-start shared-key comparison held the offered rate near 1,000
exports/second. Both candidates completed all 10,000 exports. The 10-second
cache reduced export p95 from 162.3 ms to 29.8 ms and retryable saturation
attempts from 4,315 to 68; backend peak CPU fell from 34.18% to 24.08%. Query
p95 was 51.8 ms with caching versus 45.4 ms without caching. That single-run
14.1% difference exceeds the plan's eventual 10% gate, so repeated runs and
the historical warm-cache comparison remain required before ADR acceptance.

The revised harness also created 100 distinct real API keys. With deterministic
per-exporter retry jitter, synchronized and staggered runs each completed all
5,000 exports at roughly 1,000 exports/second. They observed 225 and 231
retryable cold-path rejections respectively, while peak ingestion memory stayed
between 19.21 and 28.32 MiB. The last successfully admitted post-deletion
exports completed at 9.948 and 9.951 seconds, inside the 10-second fixed window;
the first rejection responses arrived at 10.011 and 10.006 seconds.

An adversarial unjittered distinct-key run exhausted ten retries for 10 of
5,000 exports because every rejected exporter re-entered on the same backoff
boundaries. This validates the intended division of responsibility: ingestion
kept only 32 cold requests and eight refreshes, while a realistic jittered
exporter retry policy made progress without increasing server memory bounds.

Final repository-owned evidence consists of:

- the [42-scenario candidate matrix](STUDIO_INGESTION_API_KEY_AUTHORIZATION_MATRIX_2026-07-16.json),
  which records every candidate and required workload dimension;
- the [60-second resource and reconnect soak](STUDIO_INGESTION_API_KEY_AUTHORIZATION_SOAK_2026-07-16.json),
  including 6,000 exports, 1,812 queries, failure probes, WAL durability, and 20
  endpoint restarts; and
- the [raw pinned historical/current runs](evidence/studio-ingestion-auth-2026-07-16/README.md),
  including ingest-only and mixed-query baselines.

The historical and accepted designs each have three equal-rate mixed-query
runs. Historical warm-cache median throughput was 504.28 exports/second and
median query p95 was 47.02 ms. The accepted design produced 504.31
exports/second and 40.68 ms. Its median peak ingestion memory was 24.11 MiB
versus 55.21 MiB historically, and its median maximum TCP records were seven
versus 56. The single high-latency accepted run is retained in raw evidence;
the median gate prevents it from being hidden or over-weighted.

The pinned no-cache/fresh-channel baseline completed only 211.98 exports/second
under the 500-export/second offered rate, with 408.31 ms export p95 and 4,991
TCP records by the end. No-cache with the reusable channel completed 500.95
exports/second with 81.92 ms p95 and at most six TCP records. This isolates and
proves the transport-lifecycle improvement.

The five-second TTL was rejected despite passing short-cadence tests. With 100
distinct exporters waiting five seconds after each completed export, it made
400 backend validations for 400 exports. Ten seconds made 200, eliminated the
two overload retries, reduced export p95 from 15.19 to 8.44 ms, and used less
peak ingestion memory. Fifteen and 30 seconds provided no material performance
gain worth their longer revocation windows.

Capacity 1,024 avoided the 44 second-round revalidations observed with 256
entries across 300 active keys. Three-run candidate medians select eight
refreshes and 32 pending requests. A controlled 1.25-second backend delay
selects the two-second deadline. The soak proves the selected process remains
well inside its memory envelope and does not leak descriptors, threads, or
established connections across endpoint restarts.

ADR-009 is Accepted and all work packages and acceptance gates are complete.

## Completion criteria

This plan is complete because:

1. ADR-009 is Accepted with measured numeric defaults.
2. The reusable channel, bounded positive cache, coalescing, deadline, and
   validation limit are implemented.
3. Revocation, outage, overload, reconnect, expiration, and cache-capacity
   behavior have focused tests.
4. The one-vCPU/1GB benchmark and mixed-query workload pass their gates.
5. Canonical deployments and operator documentation expose one consistent
   revocation contract.
6. The comprehensive review ledger records L5 as fully resolved with links to
   the accepted ADR and evidence.
