---
name: ingestion-flow
description: Use when changing or reviewing the OTLP ingestion path, segmented WAL, Parquet flush behavior, hot snapshots, recent_cold_paths bridging, or ingestion-related proto contracts. Owns ingestion runtime flow and cross-service storage/query boundaries, not general backend or frontend work.
---

# Ingestion Flow

## Use This Skill When

- The task touches `ingestion/`.
- The task changes WAL, segmenting, flush triggers, hot snapshots, backpressure, or recent cold file bridging.
- The task changes `proto/` contracts used by ingestion and the backend.
- The task changes backend code that directly depends on ingestion query semantics.

## Do Not Use This Skill When

- The task is normal FastAPI feature or CRUD work in `backend/`.
- The task is frontend UI or state-management work in `frontend/`.
- The task is primarily an auth/security review with no ingestion-path changes.

## Owned Paths

- `ingestion/`
- `proto/`
- Backend files that directly participate in ingestion query bridging:
  - `backend/app/features/span_ingestion/`
  - `backend/app/features/otel_spans/`

## Workflow

1. Start from the code path, not the prose docs.
2. Trace the end-to-end flow before editing:
   - OTLP receive
   - WAL write
   - cold flush
   - hot snapshot
   - backend query registration
   - deduplication / recent-cold bridging
3. Use ADRs only for decisions and invariants:
   - `ingestion/adr/001-segmented-wal-architecture.md`
   - `ingestion/adr/002-sqlite-metadata-index.md`
   - `docs/adr/004-events-json-contract.md` when events JSON is involved
4. Treat `ingestion/src/config.rs` and the active backend code as the source of truth for defaults and behavior.
5. If a proto changes, update the owning `.proto` file and the Python generated files through the repo command, never by hand.

## Validation Expectations

- Run `cd ingestion && cargo test --locked` for ingestion-only changes.
- If backend query behavior or proto contracts changed, run the smallest relevant backend tests too.
- If Python proto generation is required, use `./run-all-proto-gen.sh`.
- Verify that docs still describe the decision, not the implementation snapshot.

## Source Of Truth Rules

- Runtime defaults live in code, especially `ingestion/src/config.rs`.
- Cross-service contracts live in `proto/` and narrow ADRs.
- Do not add mirrored architecture explanations to root docs.
