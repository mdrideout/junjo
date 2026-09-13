# Ingestion and backend performance mechanics — September 7, 2026

The maintainer accepted the preceding robustness changes and their possible
measured cost. This investigation identifies optimization targets; it does not
reopen that approval or change the historical numeric gate results. **No new
production runtime changes were applied.** All profilers and prototypes ran in
disposable builds and containers.

The earlier 12% throughput difference remains unattributed to a specific code
change. Direct instrumentation finds almost no time spent acquiring the WAL
lock or sending notifications in the measured workloads. Larger observed costs
are CPU quota throttling, synchronous storage work, per-span Python metadata
construction, and repeated query setup/execution.

The metadata-only follow-up implementation and validation are recorded in
[metadata extraction optimization](../studio-metadata-extraction-2026-09-07/README.md).

## Evidence and limits

- **19 end-to-end runs; 92,960,000 offered, acknowledged, and uniquely persisted
  spans; zero missing acknowledged spans and zero duplicate rows.** Every logical
  export and query ultimately succeeded; initial retryable attempts are retained
  separately in each result. Both services stopped before canonical delivery
  verification. No OOM kills or container restarts.
- Existing constrained profile: ingestion 0.5 CPU/350 MiB, backend 0.5 CPU/450 MiB,
  no swap. Production images, unchanged backend, identical offered work within
  each comparison. Saturation uses 50 exporters × 4,000 exports × 32 spans;
  mixed load uses 50 × 300 × 32, a 100 ms cadence, and two service-query workers.
- Rust profiles compare the original and accepted lock-release implementations
  with identical instrumentation. Three profiled variants, two uninstrumented
  ingestion prototypes, and separate CPU-allocation diagnostics were exercised.
  Two alternating saturation rounds provide candidate/control observations.
- Host: Apple Silicon macOS and Docker Desktop. Unrelated host workloads remained
  active. Accepted production-image control runs alone varied from 190k to 218k
  spans/sec. These observations identify mechanisms, not precise fleet capacity.
- Rust phase timers add overhead, nest, and cover the process lifetime, including
  idle/shutdown. Backend thread CPU excludes native worker-thread CPU. Neither
  should be summed indiscriminately or substituted for workload cgroup CPU.
- The first live cProfile capture contains unrelated callbacks; it is retained
  for transparency but excluded from exclusive cost attribution. A separate
  offline reader profile provides a cleaner view. Offline results are not E2E
  performance proof.

[Machine-readable summary](summary.json) contains all run metrics and extracted
profiles. [Provenance](provenance.json) records source and image identities.
Individual results and complete service logs are in `results/`.

## 1. Lock release is not a demonstrated steady-state bottleneck

In the instrumented 6.4-million-span saturation pair:

| Measurement | Original | Accepted lock release |
| --- | ---: | ---: |
| Acknowledged throughput | 207,108/s | 210,006/s |
| Ingestion workload CPU | 15.226 s | 15.108 s |
| Total WAL acquisition wait across 200,000 exports | about 10 ms | about 10 ms |
| Total notification wait across about 6,400 sends | about 3 ms | about 3 ms |
| Full notification queue observations | 0 | 0 |
| Mixed workload query p95, separate runs | 35.87 ms | 36.66 ms |

This does not prove zero regression in every workload. It shows that the
reproduced deadlock mechanism was not active here and that the notification
await itself cannot account for the measured steady-state cost in these runs.
The existing full-queue regression remains necessary.

## 2. CPU scheduling explains a large part of observed latency

The ingestion container's quota is 50,000 microseconds per 100,000-microsecond
period. The accepted profiled saturation run was throttled in 301 of 307 active
periods, accumulating 15.6 seconds of throttling during a 30.5-second workload.
Export p95 repeatedly clusters around 53 ms under this constraint.

A separate allocation diagnostic pinned **both services to the same single
virtual CPU**, retained 350+450 MiB and no swap, and compared separate half-CPU
quotas with no individual quotas. Each longer run delivered 12.8 million spans:

| Allocation on the same single vCPU | Split half-CPU quotas | Shared CPU, no individual quotas |
| --- | ---: | ---: |
| Acknowledged throughput | 191,884/s | 362,302/s |
| Workload duration | 66.71 s | 35.33 s |
| Export p95 | 52.41 ms | 6.99 ms |
| Ingestion CPU during workload | 33.17 s | 29.75 s |
| Backend CPU during workload | 9.90 s | 5.25 s |
| Peak sampled ingestion working set | 51.28 MiB | 35.07 MiB |
| Peak sampled backend working set | 323.9 MiB | 328.7 MiB |

Indexing overlapped both longer runs. However, they did **not** complete equal
amounts of metadata indexing before measurement ended; indexing completion is
not an acceptance condition of this ingestion harness. Do not present this as
an 89% improvement in fully indexed platform capacity. It demonstrates the
cost of preventing ingestion from using the backend's idle CPU allocation.

The supported deployment Compose files impose no such per-service CPU quotas.
Keep the historical split-quota benchmark as a stress profile and add a clearly
separate whole-stack single-CPU profile when measuring deployment behavior.
Do not replace its failed results with these numbers. Sharing/pinning was also
not a universal query win: one shared-CPU mixed run had 66.81 ms query p95,
versus 39.07 ms in the ordinary split/unpinned control. That comparison also
changes affinity, so it is a warning against universal conclusions, not an
isolated estimate of the quota effect on queries.

## 3. Synchronous work delays the single ingestion worker

The profiled container reports one available CPU; the default Tokio runtime
therefore has one worker. Conversion, IPC creation, cold Parquet writing, and
snapshot creation execute synchronously. A request can wait to be polled
before its lock-acquisition timer even starts. Tiny measured lock waits do not
mean storage work cannot delay requests.

In the accepted saturation profile, conversion consumed 3.06 seconds of thread
CPU, WAL writes 3.88 seconds, and cold flushes 2.93 seconds. The WAL-write total
includes about 2.77 seconds of IPC writing and 0.69 seconds of Arrow building;
these are nested costs. The longest cold-flush critical section was 170 ms.
In mixed load, 31 snapshot builds consumed 0.634 seconds of thread CPU and the
longest build took 45.8 ms. These are real latency contributors under the tested
constraints, not an argument for stronger durability or more frequent flushing.

Moving cold work outside the WAL lock or executor is **not the first proposed
change**: the current lock also protects segment lifetime and the recent-cold
handoff. Merely moving work to another thread does not remove its CPU cost,
and on one CPU can trade throughput or memory for responsiveness.

## 4. Backend metadata extraction is a strong optimization target

In the non-cProfile mixed profile, reading three cold files into Python metadata
used **2.475 seconds of reader-thread CPU**, versus **0.137 seconds** for the
metadata-index function: about **18×**. The index function includes the SQLite
updates. SQLite transaction tuning is therefore a lower priority in this shape.

The reader materializes nine Python column lists, constructs two Python
datetimes per span, parses the attributes JSON, and creates one 15-field
`SpanMetadata` object per span. The indexer then walks the list repeatedly to
produce much smaller trace/service/classification summaries. Backend cgroup
memory reached the 450 MiB limit and recorded memory-limit events during mixed
and saturation workloads, without an OOM kill. The limit includes file cache;
it must not be described as 450 MiB of Python objects alone.

A stopped-stack synthetic file with 121,600 rows was read in six fresh
0.5-CPU/450-MiB processes, alternating the existing reader and a slotted-dataclass
prototype. All 15 returned span fields had identical semantic hashes.

| Offline reader median, three runs each | Existing | Slotted objects |
| --- | ---: | ---: |
| CPU | 0.826 s | 0.817 s |
| Wall time | 1.683 s | 1.673 s |
| Peak process RSS | 237.43 MiB | 231.66 MiB |

Slots alone save approximately 5.8 MiB of peak RSS here and show little speed
change; this is not a compelling standalone optimization. RSS also includes
Arrow initialization and native allocations. The clean offline profile confirms
243,200 timestamp conversions and 121,600 JSON parses. Avoiding unnecessary
per-span materialization/conversion is the more substantial opportunity.

## 5. Service discovery repeats avoidable query work

The mixed profile recorded 815 service-list requests but 1,395 DataFusion
contexts and distinct-service queries. The caller constructs separate query
objects for recent-cold files and the hot snapshot, even though
`UnifiedSpanQuery.query_distinct_service_names()` already supports both tiers.
Snapshot caching reduced actual snapshot builds to 31, but each request still
re-registered and queried its inputs.

The synchronous distinct-service query calls consumed 3.81 seconds of aggregate
wall time and at least 1.65 seconds of calling-thread CPU. Registration was also
measurable. These calls run directly in an async request handler, so they can
hold up other requests on that event loop. First test one combined hot/recent
query per request. Preserve current source selection, fresh snapshot handling,
and failure behavior; do not solve it by extending a stale-result cache TTL.
Combining queries has not yet been benchmarked and is not a promised gain.

## Prototypes that did not establish a win

| Uninstrumented saturation, two rounds | Median spans/sec | Change from accepted control | Ingestion CPU per span |
| --- | ---: | ---: | ---: |
| Accepted implementation | 204,118 | — | 2.437 µs |
| Buffer Arrow IPC writes | 175,412 | −14.1% | 2.812 µs |
| Serialize shared resource metadata once | 193,866 | −5.0% | 2.557 µs |

Buffering reduced observed write calls by about 44% in the instrumented run,
but added buffering/copying and did not reduce measured CPU or improve E2E
throughput. The resource prototype still clones owned strings for every span;
its avoided serialization work did not produce a demonstrated overall gain.
Host variability limits exact attribution, but neither candidate earns a
production change. Both passed 25 Rust unit and 14 integration tests, plus their
E2E delivery checks. Those passing tests are not performance approval.

## Recommended order and validation

1. **Reduce metadata-reader work and temporary memory.** First inspect which
   columns/objects consumers actually need; preserve all current service, trace,
   LLM, workflow and agent classification semantics. Prototype column-oriented
   summaries or fewer timestamp/object conversions without changing Parquet or
   telemetry contracts. Slotted objects alone are insufficient evidence.
2. **Combine the two service-discovery queries.** This is a smaller, well-located
   candidate using existing capabilities, with no new persistent cache or TTL.
   Check hot-only, recent-only, overlapping tiers, rollover and error behavior.
3. **Then revisit synchronous ingestion storage costs**, only if the cheaper
   backend changes leave a demonstrated latency problem. Preserve the accepted
   durability, batching, compression and handoff behavior.

For each candidate, run relevant semantic tests first, then alternating
uninstrumented baseline/candidate E2E runs with identical workload, warmup and
resource settings. Keep both split-quota stress and shared single-CPU results
explicitly labelled. Include sustained ingestion through repeated cold/indexer
cycles, concurrent queries, CPU per persisted span, export/query p95 and p99,
working set/cgroup pressure, retries and canonical delivery. Metadata changes
also require equal **completed indexed rows and catch-up work**, which the
current ingestion acceptance check alone does not establish. Include diverse
resource attributes and real agent/workflow-shaped telemetry before concluding
that the simpler synthetic workload represents all production traffic.

No changes to flush cadence, fsync, queue capacity, allocator, deployment
resources or production telemetry contracts resulted from this investigation.

## Reproduction material

`patches/` contains diagnostic/prototype diffs against the accepted worktree;
`diagnostics/` contains the actual session drivers, Docker build logs, prototype
test logs, and diagnostic harness with full cgroup counters. The original
absolute session paths are retained in these scripts; adapt them when replaying.
The pinned images must match provenance for direct comparisons. Apply one
prototype patch at a time to an isolated copy of the accepted worktree, then
build its ingestion production image using the existing Studio Dockerfile.
Do not apply the diagnostic patches to a production checkout.

`offline/` contains only a small synthetic Parquet fixture copied after the
owned stack stopped, its offline reader profile and pstats. The normal reader,
slots-only reader, and offline drivers are in `diagnostics/`. Performance runs
were sequential, with no overlapping builds or test suites. The user's original
Studio stack was left running throughout.
