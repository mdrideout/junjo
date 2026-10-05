# Rust backend measurement slice — October 3, 2026

This is the measured comparison that work package 2 of the
[Studio backend Rust migration plan](../../STUDIO_BACKEND_RUST_MIGRATION.md)
requires before the full port may proceed. The plan sets no pass threshold.
The results are presented here and the maintainer decides.

The Rust slice completed the same work as the Python backend in every run.

- **Backend CPU**: 42% less while ingesting with concurrent queries, and 79%
  less in the index-completion workload.
- **Backend memory**: peak sampled memory of 48–100 MiB against 310–375 MiB.
  About 5 MiB of anonymous memory at idle against 98 MiB.
- **Service queries**: p95 of 15.6 ms against 28.7 ms, with 11% more queries
  answered in the same window.
- **Ingestion with separate CPU quotas**: throughput, ingestion CPU, and export
  latency were unchanged once host CPU speed was held constant.
- **Ingestion on one shared CPU**: equal when no indexing overlaps an ingestion
  burst. When an indexing cycle lands inside the burst, ingestion slows by 6%
  beside the Rust backend and by 33% beside the Python backend.

**59 runs; 45,120,000 offered spans, all acknowledged, all verified in
canonical storage after shutdown, and all indexed.** No OOM kills and no
container restarts. The Python backend reached its 450 MiB limit in 8 of its
21 runs, which forces reclaim but did not kill it. The Rust slice never
reached the limit in 38 runs.

## What was compared

- **Python**: the production image built from the repository at commit
  `1faadb5`.
- **Rust**: the slice, then in `apps/studio/backend-rs` and now in
  `apps/studio/backend`, default release profile and
  system allocator. It contains configuration, both SQLite databases,
  first-user setup with a server-side session, API-key management, the internal
  `ValidateApiKey` service, the metadata indexer, service discovery, and the
  trace span query. It does not yet contain the rest of the HTTP surface, the
  evidence logic, or static UI serving.
- **Ingestion**: one production image from the same commit, identical for every
  run.
- **Profiles**: memory is 450 MiB for the backend and 350 MiB for ingestion,
  with no swap, in both.
  - Split quota: each service has its own 0.5 CPU quota. Results are from this
    profile unless a section says otherwise.
  - Single CPU: both services share one CPU and have no individual quota.
- **Workloads**: the September 2026 shapes, with their classification
  attributes over three services.
  - Mixed: 50 exporters, 300 exports each, 32 spans per export, 100 ms cadence,
    two service-query workers. 480,000 spans in 6 cold files.
  - Index completion: 50 exporters, 800 exports each, 32 spans per export,
    unpaced, no queries. 1,280,000 spans in 16 cold files.
- **Completed work** means every offered span was acknowledged, verified in
  canonical WAL and Parquet after both services stopped, and present in the
  metadata index.
- **Order**: runs were sequential, and Python and Rust runs alternated within
  each comparison batch. No builds or test suites ran during measurement.

Both backends produced identical index contents in all 59 runs: the same file,
row, and trace counts, the same per-service span counts, and the same LLM,
Workflow, and Agent classification counts.

### What each window contains

Each run has three windows, and they matter when reading the tables.

1. **Before ingestion**: 20 seconds after setup, except in the few runs noted
   below that shift it. In the mixed workload the two query workers are
   already running against an empty system, so this is not an idle reading.
   The index-completion workload has no query workers, and its reading is
   idle.
2. **Ingestion**: the offered work. 29.9 seconds in the mixed workload. In the
   index-completion workload it is a burst of about 8 seconds on the split
   quota profile and about 4 seconds on the single CPU profile.
3. **Catch-up**: from the end of ingestion until every span is in the metadata
   index. Query workers keep running. Its length is set mostly by the
   indexer's polling cadence, as shown below, and it differs between the
   backends.

Query counts and latencies are reported for windows 1 and 2 together, which
are the same length for both backends. They include 20 seconds of queries
against an empty system, so both are lower than under ingestion alone.

## Host CPU speed has to be held constant

The first paired runs showed ingestion using 26% more CPU beside the Rust
backend, with higher export latency. The ingestion binary is identical, so
this was investigated before anything else was read from the results.

- Hot snapshot builds were the same: 29 beside Python, 30 beside Rust.
- With no query workers at all, ingestion used *more* CPU for *less* work:
  4.8–5.3 s, against 2.9–3.8 s with queries.
- With four busy threads running in a sibling container for the whole batch,
  the difference disappeared: ingestion used 2.48 s beside Python and 2.51 s
  beside Rust, and export p95 was 9.7 ms and 9.3 ms.

On this host a lighter overall load lets the CPUs run slower, so identical work
costs more CPU-seconds. The Rust backend lowers the overall load, which made
ingestion look more expensive. CPU and latency comparisons below therefore use
the loaded-host runs. The unloaded runs are retained and shown separately.
Memory results are the same in both conditions.

## Results on the split quota profile

Loaded host. Medians, with ranges in parentheses.

### Mixed workload

Python: two runs. Rust: five runs.

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 480,000 | 480,000 | — |
| Backend CPU during ingestion | 7.55 s | 4.38 s (4.27–4.91) | −42% |
| Backend CPU through completed indexing | 11.62 s | 5.32 s (5.24–5.93) | −54% |
| Peak sampled backend memory | 311.6 MiB | 67.8 MiB (49.4–100.0) | −78% |
| Backend cgroup peak, including file cache | 445.9 MiB | 106.7 MiB (96.1–113.3) | −76% |
| Backend anonymous memory after the work | 245.1 MiB | 11.1 MiB (11.0–11.6) | −95% |
| Backend process RSS after the work | 328.8 MiB | 59.8 MiB (56.3–62.3) | −82% |
| Service queries answered before and during ingestion | 1,519 | 1,682 (1,623–1,693) | +11% |
| Service-query p95, same window | 28.7 ms | 15.6 ms (14.2–26.5) | −46% |
| Service-query p99, same window | 58.0 ms | 40.0 ms (37.4–62.9) | −31% |
| Export p95 | 9.74 ms | 9.28 ms (7.54–9.88) | flat |
| Export p99 | 37.7 ms (27.3–48.2) | 44.7 ms (13.4–48.2) | within range |
| Ingestion CPU during ingestion | 2.48 s | 2.51 s (2.39–2.81) | flat |
| Backend CPU throttled by its quota, through completed indexing | 2.19 s | 0.36 s (0.27–0.52) | −84% |

Read the two CPU rows together.

- **During ingestion** is the same 29.9 seconds for both. Python indexed one of
  the six files inside it and Rust none, and Rust answered more queries.
- **Through completed indexing** includes all six files for both. Python's
  catch-up lasted about 11 seconds against about 4, and query workers kept
  running in it, so Python's figure includes about 7 more seconds of answering
  queries.

Across the whole run, including catch-up, query p95 was 31.8 ms against
16.6 ms and p99 was 120.4 ms against 44.5 ms. Those windows differ in length,
so they are not in the table.

### Index-completion workload

Python: one run. Rust: two runs. This workload has no query workers, so the
work is exactly equal and the before-ingestion readings are idle readings.

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 1,280,000 | 1,280,000 | — |
| Backend CPU through completed indexing | 4.49 s | 0.94 s (0.89–0.98) | −79% |
| Peak sampled backend memory | 374.6 MiB | 48.7 MiB (48.4–48.9) | −87% |
| Backend cgroup peak, including file cache | 450.0 MiB (at the limit) | 75.5 MiB (74.6–76.3) | −83% |
| Backend anonymous memory at idle | 98.4 MiB | 5.1 MiB (5.0–5.1) | −95% |
| Backend process RSS at idle | 159.5 MiB | 20.8 MiB (20.7–20.8) | −87% |
| Backend anonymous memory after the work | 244.1 MiB | 16.5 MiB | −93% |
| Backend process RSS after the work | 297.1 MiB | 31.2 MiB (30.9–31.5) | −89% |
| Acknowledged ingestion rate | 157,806 spans/s | 157,676 spans/s (154,687–160,665) | flat |
| Export p95 | 55.96 ms | 55.75 ms (55.08–56.42) | flat |
| Ingestion CPU during ingestion | 4.07 s | 4.06 s (3.99–4.13) | flat |

The before-ingestion medians in the mixed workload were within 1 MiB of these
idle readings for both backends.

A third Rust run used a 5-second period before ingestion. It used 0.79 s of
backend CPU and peaked at 68.5 MiB, and it is discussed below.

### Completion time is set by the polling cadence

| Time to complete ingestion and indexing | Python | Rust |
| --- | ---: | ---: |
| Mixed, 6 cold files | 41.2 s | 34.2 s (33.2–34.3) |
| Index completion, 16 cold files | 45.7 s | 64.0 s (63.7–64.3) |

Neither row measures indexing speed. Both backends index at most 10 files per
cycle and wait 30 seconds between cycles, so the total depends on how many
files exist when each cycle fires. The two backends start at different speeds,
so their cycles fall at different points in the work. The observer records the
index once per second.

Mixed workload:

- Python had indexed one file when ingestion ended. Its next cycle fired about
  8 seconds later and indexed the other five in about 3 seconds.
- Rust had indexed none. Its next cycle fired about 3 seconds after ingestion
  ended and indexed all six within about a second.

About 5 of the 7 seconds between them is when the timer happened to fire.

Index-completion workload:

- Python finished in 45.7–46.7 s in all four of its split quota runs across
  both host conditions. The cycle that fired during ingestion reached 10 files
  at one to two files per second. The next cycle, 30 seconds later, indexed
  the other 6.
- Rust finished in 63.7–64.9 s in seven of its nine split quota runs. A cycle
  fired earlier in ingestion and found 4 or 5 files. The next cycle indexed 10
  files, the per-cycle limit, within one or two seconds. The last one or two
  files waited another 30 seconds.
- The other two Rust runs finished in 35.1 s and 50.0 s. In the first, 6 files
  were ready for the first cycle, so two cycles were enough. The second used a
  5-second period before ingestion instead of 20, which moved the cycles
  relative to the work.

Backend CPU and the per-cycle rate are the indexing measurements. The cadence
and the per-cycle limit are existing settings and were not changed.

## Results on the single CPU profile

Both services share one CPU with no individual quota, as a one-CPU host would
run them. Loaded host, with the load kept off the measured CPU. Two runs in
every cell.

### Mixed workload

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 480,000 | 480,000 | — |
| Backend CPU during ingestion | 6.47 s (6.22–6.72) | 4.12 s (4.11–4.13) | −36% |
| Backend CPU through completed indexing | 10.09 s (9.54–10.65) | 5.03 s (5.02–5.03) | −50% |
| Peak sampled backend memory | 268.6 MiB (216.2–320.9) | 79.3 MiB (58.8–99.8) | −70% |
| Backend cgroup peak, including file cache | 433.6 MiB (420.0–447.2) | 111.6 MiB (110.7–112.4) | −74% |
| Backend process RSS after the work | 276.4 MiB (264.8–288.0) | 56.2 MiB (50.3–62.1) | −80% |
| Service queries answered before and during ingestion | 1,553 (1,549–1,556) | 1,698 (1,683–1,713) | +9% |
| Service-query p95, same window | 29.4 ms (28.9–29.9) | 14.9 ms (14.4–15.4) | −49% |
| Service-query p99, same window | 51.5 ms (50.9–52.0) | 34.6 ms (34.5–34.6) | −33% |
| Export p95 | 10.14 ms (9.64–10.65) | 8.91 ms (8.40–9.43) | −12% |
| Export p99 | 48.5 ms (48.5–48.6) | 27.2 ms (21.3–33.0) | −44% |
| Ingestion CPU during ingestion | 2.43 s (2.36–2.51) | 2.37 s (2.35–2.39) | flat |

With one CPU to share, the CPU the backend does not use is available to
ingestion, and export latency falls. Python's catch-up lasted about 8 seconds
against about 4, so its second CPU row again covers a longer window.

### Index-completion workload

Unpaced ingestion finishes in about 4 seconds here. Whether an indexing cycle
fires inside that burst decides how much CPU ingestion gets. With the default
20-second period before ingestion, a Rust cycle fired inside the burst and the
Python cycle fired just after it. Shifting that period by a few seconds moved
each backend into the other position.

| | Python | Rust |
| --- | ---: | ---: |
| **No indexing cycle inside the burst** | | |
| Acknowledged ingestion rate | 320,168 spans/s (303,139–337,196) | 317,915 spans/s (316,824–319,006) |
| Export p95 | 5.93 ms (5.23–6.63) | 5.89 ms (5.86–5.92) |
| Backend CPU during ingestion | 0.04 s | 0.03 s |
| **An indexing cycle inside the burst** | | |
| Files indexed inside the burst | 7–8 | 10 |
| Backend CPU during ingestion | 2.00 s (1.98–2.03) | 0.32 s |
| Acknowledged ingestion rate | 215,181 spans/s (206,721–223,641) | 299,484 spans/s (292,212–306,756) |
| Export p95 | 11.66 ms (11.65–11.67) | 9.16 ms (8.47–9.85) |
| Change in ingestion rate | −33% | −6% |

Read in the default position alone, ingestion looks 6% slower beside the Rust
backend. That difference is the timer, not the backend: without an overlapping
cycle the two are equal, and with one the Python backend costs ingestion more
than five times as much.

For the equal work of the default position, through completed indexing:

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Backend CPU through completed indexing | 4.14 s (4.14–4.15) | 0.67 s (0.66–0.68) | −84% |
| Peak sampled backend memory | 263.1 MiB (252.5–273.6) | 44.6 MiB (41.6–47.5) | −83% |
| Backend cgroup peak, including file cache | 353.4 MiB (315.0–391.7) | 72.8 MiB (65.3–80.2) | −79% |
| Backend process RSS after the work | 216.3 MiB (205.4–227.1) | 31.2 MiB (31.0–31.3) | −86% |

## Results on the unloaded host

Retained for transparency. Split quota profile, two runs each, mixed workload.

| | Python | Rust |
| --- | ---: | ---: |
| Backend CPU during ingestion | 8.35 s | 6.31 s |
| Backend CPU through completed indexing | 12.73 s | 7.48 s |
| Peak sampled backend memory | 345.3 MiB | 82.2 MiB |
| Service-query p95, before and during ingestion | 33.2 ms | 20.5 ms |
| Export p95 | 12.94 ms | 15.49 ms |
| Export p99 | 31.9 ms | 76.6 ms |
| Ingestion CPU during ingestion | 2.97 s | 3.73 s |

The last three rows are the host effect described above, not a property of
either backend. The backend CPU saving is understated here for the same
reason.

The same cadence with no query workers was also run on the unloaded host, two
runs each. The work is exactly equal: API-key validation and indexing six
files. Backend CPU through completed indexing was 2.16 s for Python and 0.59 s
for Rust.

## Rust memory floor by layer

From one run with startup logging enabled. The process reports its own
resident memory at each stage.

| Stage | Resident | Anonymous | File-backed |
| --- | ---: | ---: | ---: |
| Runtime started | 13.8 MiB | 4.0 MiB | 9.8 MiB |
| Listeners bound | 13.9 MiB | 4.0 MiB | 9.9 MiB |
| Both SQLite databases open | 16.2 MiB | 4.5 MiB | 11.7 MiB |
| DataFusion runtime created | 17.2 MiB | 4.5 MiB | 12.8 MiB |
| Servers started | 18.7 MiB | 4.5 MiB | 14.2 MiB |
| First DataFusion query completed | 50.5 MiB | 5.6 MiB | 44.9 MiB |

The heap stays small throughout. Almost all of the growth is file-backed:
30.7 MiB between serving and the first DataFusion query, which first runs once
ingestion has produced data.

The file-backed share was not broken down by mapping. It is consistent with
code pages of the binary itself. The default binary is 163 MB, 111 MB of it
code. The link-time-optimized build, which is 72 MB smaller, lowered resident
memory after the work by 19 MiB while anonymous memory moved by 1.4 MiB. The
metadata database is also memory-mapped, which adds file-backed memory as the
index grows. File-backed memory is reclaimable under pressure, but it is most
of the footprint.

## Settings compared one at a time

Split quota profile, loaded host, mixed workload, against the default Rust
build.

| Setting | Runs | Result |
| --- | ---: | --- |
| Allocator: `mimalloc` instead of the system allocator | 2 | Anonymous memory after the work rose from 11.1 MiB to 61.5 MiB and cgroup peak from 107 MiB to 169 MiB. Backend CPU was 5.48 s against 5.32 s. No benefit here. |
| Link-time optimization with one codegen unit | 3 | Binary 163 MB to 91 MB. Process RSS after the work 59.8 MiB to 41.0 MiB. Cgroup peak 107 MiB to 80 MiB. Backend CPU 4.96 s against 5.32 s. Adds about six minutes to each release build. |
| DataFusion runtime caches disabled | 1 | Backend CPU rose from 5.32 s to 6.00 s. Process RSS after the work was 59.1 MiB against 59.8 MiB, so no memory saving was visible. |
| Parquet filter pushdown enabled | 1 | Within the run-to-run range of the default build. This workload's query has no filter, so it does not exercise the setting. |
| Two runtime worker threads instead of one | 2 | No clear difference in `ValidateApiKey` latency. See below. |

Two of the five link-time-optimization runs, one per workload, were disturbed:
ingestion CPU on the unchanged ingestion binary was about 30% above the median
of the other runs of that workload. They are included in the medians above.

## `ValidateApiKey` latency while queries run

Mixed workload with one API key per exporter, routed through the counting
proxy. The proxy runs at 0.10 CPU and both services at 0.45, and the latency
includes the proxy hop. Each run makes 150 validations.

| | Runs | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Python | 3 | 7.2 ms (6.3–23.1) | 62.1 ms (42.4–75.7) |
| Rust, one worker thread | 3 | 9.8 ms (6.7–10.7) | 44.2 ms (42.7–44.7) |
| Rust, two worker threads | 2 | 8.0 ms (7.3–8.8) | 44.9 ms (44.9–45.0) |

The ranges overlap and every value is far inside the two-second deadline in
Studio ADR-009. This evidence does not show a need for a separate query
runtime.

## Retries and delivery

Every export succeeded and every acknowledged span was found in canonical
storage, with no duplicates.

Every retried attempt was a retryable `UNAVAILABLE` at the start of a run, when
all 50 exporters first present their keys and ingestion's bounded validation
queue turns the overflow away.

| Retried attempts per run | Python | Rust |
| --- | ---: | ---: |
| Mixed cadence | 21–54 | 0–54 |
| Index completion | 18 | 18–26 |
| Mixed, through the counting proxy | 117–120 | 105–122 |

## Frontend container

The plan's baseline also records the container that serving the UI from the
backend would remove. The production frontend image built from the same commit
holds about 10 MiB: 9.9 MiB sampled and a cgroup peak of 13–14 MiB. That was
the same with one CPU visible and with all twelve, and unchanged after 400
page requests.

The Rust slice does not serve the UI yet, so this is the size of that
container, not a measured saving.

## Slice validation

- 66 Rust tests pass, covering configuration, schema creation and refusal,
  metadata statements, span classification, the Parquet reader, the indexer
  cycle and thread, the two-tier query, the session store, the internal gRPC
  service over a real transport, and the HTTP surface.
- `cargo clippy --all-targets` and `cargo fmt --check` are clean.
- The harness's existing delivery tests pass with the new setup-path setting.
- Studio's full validation script passes on the same working tree: 938 backend
  tests, the ingestion tests, 250 frontend tests with lint and build, the
  contract tests, and the proto check. The Python backend is unchanged.

## Limits

- This is a slice. The harness's only query is service discovery, so the trace
  query, evidence assembly, and evaluation paths are not measured.
- One host: Apple Silicon macOS with OrbStack, 12 CPUs, and 15 unrelated
  containers running. Run counts are small. Ranges are shown wherever more
  than one run exists.
- In the mixed workload the query workers start before the 20-second
  observation and stop only when indexing completes. The windows are described
  above. No latency figure here covers ingestion alone.
- The index-completion observer runs in a sidecar container here. In September
  it ran inside the backend. Absolute numbers are therefore not directly
  comparable with the September evidence.
- The Rust result includes the DataFusion upgrade from 50.2 to 55.1. The two
  effects were not separated, because no regression appeared.
- Docker's sampled memory is a container working-set figure, not process RSS.
  Both are reported.
- The base Compose file sets glibc allocator variables for the backend service.
  They applied to the Rust system-allocator build as well.

## Decisions this evidence informs

The plan asks for these to be presented, not selected.

1. Whether the full port continues.
2. Allocator. The system allocator used far less memory than `mimalloc`.
3. Link-time optimization. It saves about 19 MiB of resident memory and 72 MB
   of binary at about six minutes per release build.
4. DataFusion runtime caches. The defaults saved CPU at no visible memory cost.
5. Filter pushdown. It needs a filtered-query workload before it can be judged.
6. Runtime worker threads. No change is indicated.

## Reproduction

- [Summary](summary.json) holds every run's metrics and the medians. Runs are
  pooled only when their period before ingestion matches. Its
  `through_ingestion` fields cover the windows before and during ingestion.
- [Provenance](provenance.json) records the source state, image identities,
  binary sizes, host, and conditions.
  [Log-derived figures](log-derived.json) holds the values read from service
  logs, and [frontend container](frontend-container.json) holds that reading.
- The raw result of each run and the services' logs are not in the
  repository. They stay with whoever made the runs, in a `results/`
  directory here that Git ignores. The summaries hold every figure this
  document reports. The file names below identify runs in the summaries.
- Run names are
  `<condition>-<variant>-<shape>-<repetition>`. The `load` condition is the
  loaded host; `wp1`, `wp2`, and `diag` are unloaded. Variants ending in
  `shared` are the single CPU profile. The `paced` shape is the mixed cadence
  without query workers, and `mixed-proxy` routes validation through the
  counting proxy. A repetition named `idle` and a number used that many
  seconds before ingestion instead of 20.
- Service logs are written beside each result. They match the repository's
  log ignore rule and stay local, as in the September evidence.
- `diagnostics/` holds the harness patch, the completion observer, the run
  driver, the Compose overlays, the frontend reading, and the aggregation
  scripts. The run driver keeps its original session paths; adapt them when
  replaying.
- Apply `diagnostics/benchmark.patch` to a copy of
  `apps/studio/ingestion/benchmarks`. Build the Python backend, ingestion, and
  Rust images before measuring, and keep builds and test suites out of
  measurement rounds.
- Start the load container before a loaded batch and remove it afterwards. For
  the single CPU profile, pin it away from the measured CPU.
