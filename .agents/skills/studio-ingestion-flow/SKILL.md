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

## Validation

- Run `cargo test --locked` from `apps/studio/ingestion` for ingestion work.
- Run relevant backend tests when query behavior or proto contracts change.
- Use `./run-all-proto-gen.sh` from `apps/studio` when Python proto generation
  is required.
- Verify that documentation describes durable decisions rather than a runtime
  implementation snapshot.
