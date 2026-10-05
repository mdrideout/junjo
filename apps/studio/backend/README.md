# Junjo AI Studio backend

The Studio backend: one Rust service that serves the HTTP API, the Studio UI,
and the internal gRPC service that ingestion calls. Its governing documents
are:

- [Studio backend Rust migration plan](../../../docs/roadmaps/STUDIO_BACKEND_RUST_MIGRATION.md)
- [Studio ADR-011: Rust backend and single-origin Studio](../docs/adr/011-rust-backend-and-single-origin-studio.md)
- [Studio ADR-012: Studio authentication](../docs/adr/012-studio-authentication.md)

## Current state

The migration plan's status section says which work packages are done.

- `evidence` holds payload parsing, Store reconstruction, Workflow and Agent
  diagnostics, and trace evidence. It reproduces the generated projection
  files, text for text, and the invalid-fixture outcomes from the shared
  telemetry fixtures.
- `server` holds the HTTP API, UI serving, the internal `ValidateApiKey` gRPC
  service, the metadata indexer, and the two-tier span queries. Its measured
  comparison with the Python backend it replaced is recorded in
  [the measurement slice evidence](../../../docs/roadmaps/evidence/studio-backend-rust-2026-10-03/README.md)
  and [the final image evidence](../../../docs/roadmaps/evidence/studio-backend-rust-final-2026-10-04/README.md).

## Layout

- `schema/`: the only schema sources, one SQL file per database.
- `evidence/`: the pure evidence library. It performs no I/O. Its tests read
  the shared fixtures in `contracts/telemetry/fixtures`.
- `server/`: the `junjo-backend` binary. Each feature under
  `server/src/features` owns its routes, its SQL statements, and its tests.
- `Dockerfile`: built with `apps/studio` as the context, like ingestion.
- `dev-entrypoint.sh`: what the development image runs. It starts the backend
  under `cargo-watch` and forwards a stop signal to it, so the backend shuts
  down cleanly. That container compiles the backend, so it needs several GB
  of memory and runs without the production container limits.

## Logging

`JUNJO_LOG_LEVEL` and `JUNJO_LOG_FORMAT` set the level and the format. At
`info` the backend writes no line per request. A line logged while a request
is handled names the request's method and path. To log every request and
response, set `RUST_LOG=info,tower_http=debug`: `RUST_LOG` overrides the
configured level.

## Databases

[Studio ADR-011](../docs/adr/011-rust-backend-and-single-origin-studio.md)
owns the SQLite and schema decisions. Working with them:

- `schema/junjo.sql` is the application database: users, sessions, API keys,
  developer access tokens, CLI sign-ins, and evaluation data.
  `schema/metadata.sql` is the metadata index, which is derived from the cold
  Parquet files.
- To change a schema, edit its file and raise the matching version constant in
  `server/src/db/mod.rs` in the same change. There are no migration files.
- After a version change, an existing `junjo.db` is refused at startup. Reset
  the local data directory as
  [TESTING.md](../TESTING.md#local-agent-e2e-identity) describes. An existing
  `metadata.db` is deleted and rebuilt by the indexer.
- Each feature keeps its SQL beside its code and lists every statement in
  `ALL_STATEMENTS`. Tests prepare each listed statement against the schema, so
  add a new statement to its list.
- Write through a database's writer connection and read through its reader. A
  write is one closure that runs to completion on the writer. The metadata
  writer belongs to the indexer thread, so request code only reads the index.
- Tests create their own temporary databases.

## Commands

Run from this directory. The pinned toolchain installs itself on first use.
The server's build script compiles the shared protos, so `protoc` 30.2 must be
on your `PATH`; see [PROTO_VERSIONS.md](../PROTO_VERSIONS.md).

```bash
cargo test --locked
```

The cross-service tests build the ingestion release binary, which takes
minutes on a clean checkout. [TESTING.md](../TESTING.md#backend-test-layers)
describes the test layers.

```bash
cargo clippy --all-targets --locked -- -D warnings
```

```bash
cargo fmt --check
```

Print the OpenAPI document the binary serves:

```bash
cargo run -q -p junjo-backend -- openapi
```

Export that document to the committed contract and run the frontend contract
tests against it:

```bash
./scripts/validate_rest_api_contracts.sh
```

Build the image from `apps/studio`:

```bash
docker build -f backend/Dockerfile --target production -t junjo-ai-studio-app .
```
