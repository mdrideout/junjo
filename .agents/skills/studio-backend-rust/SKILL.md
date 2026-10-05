---
name: studio-backend-rust
description: Use when changing or reviewing Junjo AI Studio Rust backend routes, feature modules, SQL and schema files, the metadata indexer, DataFusion queries, evidence logic, backend API contracts, tests, or code organization.
---

# Studio Backend Rust

## Use This Skill When

- The task touches `apps/studio/backend/server/`,
  `apps/studio/backend/evidence/`, or `apps/studio/backend/schema/`.
- The task changes HTTP routes, request or response types, feature SQL, the
  schema files, the metadata indexer, DataFusion queries, evidence assembly,
  or backend-visible ingestion query behavior.
- The task changes backend tests, scripts, or organization.

## Do Not Use This Skill When

- The task is primarily ingestion runtime flow work.
- The task is primarily frontend UI or state work.
- The task is primarily an authentication review better handled by
  `studio-security-auth`.

## Workflow

1. Read `apps/studio/AGENTS.md`, then start from the touched code and nearest
   tests.
2. Use owner docs only where they constrain the work:
   - `apps/studio/docs/adr/011-rust-backend-and-single-origin-studio.md` for
     the runtime, SQLite and schema ownership, the error body, and one-origin
     routing
   - `apps/studio/backend/README.md` for layout, commands, and database
     guidance
   - `apps/studio/TESTING.md`
   - `apps/studio/ingestion/adr/002-sqlite-metadata-index.md` for indexing and
     recent-cold bridge invariants
   - `apps/studio/ingestion/adr/001-segmented-wal-architecture.md` for hot
     snapshot or WAL semantics
   - `apps/studio/docs/adr/004-events-json-contract.md` for `events_json`
3. Keep backend code explicit and single-purpose. Each feature under
   `server/src/features` owns its routes, its SQL statements, and its tests.
   Evidence logic stays in the `evidence` crate, which performs no I/O.
4. Follow the scoped runtime rules: no legacy fallbacks and no hand-written
   migrations. A schema file is the desired state of its database.
5. Pair with `studio-ingestion-flow` when changing query bridging, proto
   contracts, or hot-snapshot behavior. Its performance section also applies
   to any change to a DataFusion query, the metadata indexer, or the work a
   request does: measure it with the real-world test before proposing it.
6. Pair with `studio-security-auth` when changing an authentication trust
   boundary, layer order, session policy, or API-key validation.
7. Keep ADRs strategic and update the owning document only.
8. Never access a running backend container's bind-mounted SQLite database or
   WAL from a host process. `apps/studio/TESTING.md` owns the stopped-stack
   reset procedure.

## Validation

Run the smallest relevant checks from `apps/studio`:

- `cd backend && cargo test --locked`
- `cd backend && cargo test --locked -p junjo-evidence` when only evidence
  logic changes
- `cd backend && cargo fmt --check && cargo clippy --all-targets --locked -- -D warnings`
- `./backend/scripts/validate_rest_api_contracts.sh` when REST contracts change

The OpenAPI document and the projection files are generated and committed.
Regenerate them through their owning commands rather than editing them:
the contract script above, and the command in
`apps/studio/backend/evidence/tests/generated_projections.rs`.
