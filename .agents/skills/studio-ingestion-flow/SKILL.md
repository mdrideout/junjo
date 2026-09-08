---
name: studio-ingestion-flow
description: Use when changing or reviewing Junjo AI Studio OTLP ingestion, the segmented WAL, Parquet flush behavior, hot snapshots, recent-cold bridging, or ingestion-related proto contracts.
---

# Studio Ingestion Flow

## Use This Skill When

- The task touches `apps/studio/ingestion/`.
- The task changes WAL behavior, segmenting, flush triggers, hot snapshots,
  backpressure, or recent-cold file bridging.
- The task changes `apps/studio/proto/` contracts used by ingestion and the
  backend.
- The task changes backend code that directly depends on ingestion query
  semantics.

## Do Not Use This Skill When

- The task is ordinary FastAPI feature or CRUD work.
- The task is frontend UI or state-management work.
- The task is primarily an authentication review with no ingestion-path
  changes.

## Workflow

1. Read `apps/studio/AGENTS.md` and start from the code path.
2. Trace the relevant end-to-end path before editing: OTLP receive, WAL write,
   cold flush, hot snapshot, backend query registration, and deduplication or
   recent-cold bridging.
3. Use ADRs for decisions and invariants:
   - `apps/studio/ingestion/adr/001-segmented-wal-architecture.md`
   - `apps/studio/ingestion/adr/002-sqlite-metadata-index.md`
   - `apps/studio/docs/adr/004-events-json-contract.md` when events JSON is
     involved
4. Treat `apps/studio/ingestion/src/config.rs` and active backend code as the
   source of truth for runtime defaults and behavior.
5. Update owning proto sources and regenerate outputs through repository
   commands; never edit generated files manually.

## Performance-sensitive reviews and changes

Apply the root `AGENTS.md` product-performance requirement before selecting
ingestion or query hardening. Read `apps/studio/ingestion/benchmarks/README.md`
and the relevant accepted evidence under `docs/roadmaps/evidence/`; retrieve
the owning ADR's history when it records a rejected design or earlier tuning.

- Treat per-request flushing, flush cadence, storage synchronization, allocator
  changes, lock scope, copying, and deduplication as possible runtime costs.
  A reproduced correctness failure does not establish that a candidate fix is
  suitable for the supported low-resource deployment.
- Compare unchanged and candidate production builds on the same existing
  resource profile and equivalent workload. Include paced mixed queries,
  unpaced ingestion, sparse and full batches, serial and concurrent exporters,
  and cold rollover where affected. Retain batching and allocator settings
  unless those are the explicit subject of the experiment.
- Keep measurement rounds separate from builds, validation suites, and other
  benchmark workloads. Retain overlapping runs as diagnostics and repeat the
  affected comparisons without that interference.
- Count generated, successfully exported, and persisted spans separately.
  Record retries/failures, latency distributions, CPU time, memory, and query
  impact. A paced workload meeting its offered rate is not capacity proof.
  Use repeated measurements to distinguish a regression from baseline variation.
- Keep the accepted baseline and acceptance gates fixed during a comparison.
  Do not broaden a gate or replace the baseline to make a candidate pass;
  explain inconclusive results and any proposed tradeoff to the maintainer.
- For durability, distinguish process termination, normal shutdown, storage
  write failure, and host/storage failure. Probe partial batches and batch
  boundaries with identified spans, not only file timestamps. State which
  guarantee was actually tested and leave unapproved guarantees unchanged.

## Validation

- Run `cargo test --locked` from `apps/studio/ingestion` for ingestion work.
- Run relevant backend tests when query behavior or proto contracts change.
- Use `./run-all-proto-gen.sh` from `apps/studio` when Python proto generation
  is required.
- Verify that documentation describes durable decisions rather than a runtime
  implementation snapshot.
