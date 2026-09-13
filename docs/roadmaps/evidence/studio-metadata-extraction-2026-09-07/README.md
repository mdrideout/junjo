# Metadata extraction optimization — September 7, 2026

The change is limited to the metadata reader and its SQLite consumer. It reduces
complete file-indexing CPU by **39–63%** and peak process RSS by approximately
**30%** in three paired workloads. Source-verified mixed-load E2E comparisons
show **15% less backend CPU**, **24% less peak sampled backend memory**, and
**18% lower query p95**. Mixed-load export p95 increased by **0.9 ms**; this is
retained as a measured tradeoff, not hidden by the other improvements.

## What changed

The reader previously loaded eleven columns and constructed one fifteen-field
Python object per span. The indexer then made repeated passes over those objects
to recover file, service, trace and classification summaries.

The reader now loads only five needed columns and produces those summaries
directly. It compares integer nanosecond timestamps and creates Python datetimes
only for aggregate bounds. The indexer writes the summaries using the existing
SQLite transaction and repository operations. Returning summaries also avoids
retaining the previous file's full span-object list while the background loop
starts reading the next file.

The existing per-file/per-trace architecture in ingestion ADR-002 is unchanged.
There are no new workers, queues, caches, limits, dependencies, database schema,
Parquet/telemetry contracts, polling settings or ingestion runtime changes.
Full span payloads remain in canonical Parquet. Required Arrow/Python column
buffers and distinct trace sets still use memory proportional to their input;
this is a reduction in resource use, not a constant-memory guarantee.

## Completed read-and-index comparisons

Each measurement used a fresh production-dependency Python process in a
0.5-CPU, 450-MiB container with swap disabled. Each file contains 121,600 rows.
Three paired rounds used baseline/candidate, candidate/baseline, then
baseline/candidate order, with no simultaneous builds, suites or benchmarks.
The unchanged baseline was measured before selecting the implementation.

The timed operation includes both extraction and committed SQLite indexing.
The full contents of all seven metadata tables match between implementations,
excluding nondeterministic indexing/failure timestamps. Semantic hashes cover
values, not only row counts.

| Workload | CPU seconds, baseline → candidate | CPU change | Peak process RSS, baseline → candidate |
| --- | ---: | ---: | ---: |
| Retained synthetic ingestion file; 32 spans/trace | 0.889 → 0.329 | −63% | 233 → 163 MiB |
| Three services; workflow, agent, OpenInference and GenAI spans | 0.991 → 0.430 | −57% | 293 → 207 MiB |
| Same classifications; one distinct trace per span | 1.513 → 0.930 | −39% | 301 → 212 MiB |

The fixtures include unrelated JSON payload fields, Unicode, shared traces
across services and different trace cardinalities. These measurements do not
claim universal production capacity. The seed and generation scripts are
archived for reproduction.

## Source-verified end-to-end results

Both services retain their existing half-CPU quotas, with 350 MiB for ingestion,
450 MiB for backend, and no swap. The ingestion binary is identical for every
run. The candidate backend image derives from the pinned baseline image by
copying only the two changed runtime files. The harness checks their hashes
**inside each running container** and records effective mounts.

The mixed comparison has 50 exporters, 300 exports each, 32 spans/export,
a 100 ms cadence and two service-query workers. All 480,000 offered spans must
be acknowledged, canonically persisted and indexed. One final benchmark-only
`FlushWAL` drains the tail after offering work; the normal background indexer
then catches up while queries continue. No production cadence changes are made.
The query workload is closed-loop with the same 50 ms pause per worker; actual
completed query counts are reported, not assumed identical.

Two mixed pairs ran in opposite orders:

| Median result | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Backend CPU through completed indexing | 25.41 s | 21.67 s | −14.7% |
| Peak sampled backend working set | 439.7 MiB | 332.2 MiB | −24.5% |
| Query p95 through completed indexing | 44.26 ms | 36.16 ms | −18.3% |
| Query p95 during offered ingestion | 45.46 ms | 38.66 ms | −14.9% |
| Time to complete ingestion and indexing | 69.60 s | 62.52 s | −10.2% |
| Completed queries | 1,679 | 1,667.5 | −0.7% |
| Acknowledged ingestion rate | 16,038/s | 16,045/s | approximately flat |
| Export p95 | 5.09 ms | 6.00 ms | +0.90 ms / +17.7% |

The paced ingestion rate is not capacity proof. A separate unpaced comparison
used 1.28 million spans per build, with no concurrent queries, and waited for
all indexing to finish. Baseline → candidate:

- Backend CPU: **11.91 → 5.14 seconds** (−56.8%).
- Peak sampled backend working set: **445.6 → 319.7 MiB** (−28.3%).
- Completion time: **80.94 → 66.52 seconds** (−17.8%).
- Acknowledged ingestion: **140,868 → 145,665 spans/sec** (+3.4%).
- Export p95: **56.16 → 55.95 ms**, approximately flat.

This saturation pair is an index-completion workload, not a replacement for the
older 6.4-million-span ingestion benchmark or its historical acceptance gates.
Most saturation indexing occurs after offering exports. The longer mixed case
below exercises overlap across ordinary indexing cycles.

Seven successful source-verified E2E runs preserved and indexed **5,440,000
of 5,440,000 offered spans**, with zero duplicates, missing acknowledged spans,
OOM kills or container restarts. This includes the candidate's longer mixed
case: **960,000 spans fully persisted and indexed in 65.8 seconds**, with peak
sampled backend working set **350.8 MiB**.

### Latency limit and interpretation

The mixed export-p95 increase remains visible. The runtime ingestion code is
unchanged and ingestion CPU decreased, but these facts do not prove that the
latency difference is harmless or entirely noise. The host still had unrelated
workloads, and half-CPU quotas interact with the synchronized 100 ms cadence.
The earlier accidental same-source controls also varied substantially. Do not
advertise zero latency regression. The recommendation to retain this change is
based on the substantial CPU/memory improvements, improved query latency and
successful completed work, with this approximately 0.9 ms observation disclosed.

## Larger-load failure and diagnostic limits

A final, fully accounted baseline run offered 960,000 spans with the longer
mixed workload. **108 exports exhausted retries with `UNAVAILABLE`; four query
requests failed with transport errors.** It acknowledged 956,544 spans, and all
956,544 were verified in canonical storage after orderly shutdown. There was
no loss of acknowledged spans, OOM kill or container restart in that run.

Index catch-up was skipped after export failure. The result's
`skipped_after_failed_exports` status is authoritative: its older zero sentinel
for indexed rows is not a measurement that nothing was indexed. The archived
harness now uses null for that unmeasured value and never waits for spans that
were not acknowledged.

Earlier larger-baseline attempts were diagnostic, not successful comparison
runs. One retained a gRPC observer in the backend during catch-up; another used
a minimal observer but was manually stopped after more than 1.8 million cgroup
memory-limit events and roughly 81% kernel CPU time. It had indexed about
502,000 rows at observation. Those early attempts did not retain the export
checkpoint needed to distinguish failed delivery from unfinished indexing, so
**they do not establish an ingestion/indexing deadlock or acknowledged data
loss**. The fully accounted failure above supersedes that interpretation.

Large-payload offline stress cases are also retained separately and excluded
from paired successful-run medians. Exit 137 without an OOM flag is not described
as proof of an OOM kill. Operator-stopped memory-pressure cases are explicitly
marked; they are not assigned a completed throughput or speedup ratio.

## Validation and benchmark corrections

- Studio full validation passed: **938 backend tests**, two existing skips;
  **25 Rust unit + 14 integration tests**; **250 frontend tests**; the 31-test
  contract subset; backend/frontend lint and formatting, frontend production
  build, and unchanged regenerated protocol artifacts. The existing local
  protoc-version warning remained; generation produced no contract changes.
- Three new regressions cover exact SQLite selection contents across services
  and row groups, negative/sub-microsecond timestamp bounds, duplicate traces,
  OpenInference/GenAI/workflow/agent classifications, invalid/missing attributes,
  transaction rollback and empty-file rejection.
- The first six E2E runs inherited development's backend source bind mount.
  Both image labels therefore loaded candidate source. They are excluded from
  all comparisons and retained under `diagnostic-source-mount/`. Image IDs alone
  are insufficient evidence when a source mount overrides the image.
- Valid runs replace development source mounts, verify source hashes before
  offering work, and retain mount/source evidence. The catch-up observer releases
  gRPC modules with process replacement and waits using only standard-library
  SQLite/cgroup reads inside the disposable backend. Its small resource cost is
  included for both variants. Host processes never read live backend SQLite.
- Canonical delivery verification happens only after both owned services stop.
  The user's existing Studio stack and unrelated containers were not restarted.

## Reproduction and evidence

[Summary](summary.json) contains paired medians, individual E2E metrics and the
fully accounted failed baseline. [Provenance](provenance.json) records image,
source and fixture hashes. Raw outputs and service logs are in `results/`;
baseline/candidate source snapshots and the two-file Docker build recipe are
also archived. `diagnostics/` retains the actual session scripts, validation
log, memory-pressure evidence and a patch for the diagnostic harness.

The scripts retain the original absolute session paths. To replay, restore the
seed, baseline/candidate sources and drivers into a disposable directory, adapt
those paths, and generate fixtures with the pinned production dependencies.
Apply `diagnostics/benchmark.patch` to a copy of the repository's ingestion
benchmark directory. Keep failed and successful shapes separate, assert source
hashes and effective limits, and run builds/tests separately from measurements.
No release, deployment, query consolidation or further ingestion optimization
is included in this work.
