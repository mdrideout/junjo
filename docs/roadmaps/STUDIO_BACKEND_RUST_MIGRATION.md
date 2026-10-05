# Studio backend Rust migration plan

- Status: Implemented, not yet committed or released. All eleven work
  packages are complete. The port was built from Studio 0.84.1 and then
  brought up to Studio 0.85.0 and telemetry contract 3; see "Catch-up to
  Studio 0.85.0 and telemetry contract 3". The measured comparisons are
  [the measurement slice evidence](evidence/studio-backend-rust-2026-10-03/README.md),
  on which the maintainer decided on 2026-10-03 to continue, and
  [the final image evidence](evidence/studio-backend-rust-final-2026-10-04/README.md).
  An audit on 2026-10-04 fixed the defects it confirmed and recorded what it
  left; see "Audit, 2026-10-04". Three query changes that followed from it
  were measured with the real frontend and adopted the same day, and that
  test is now a repository tool. What remains is the maintainer's: the decisions
  listed there, the two checks only GitHub can run under work package 7, and
  release preparation
- Date: 2026-10-03
- Owners: Junjo Studio backend. Ingestion, frontend, the Python SDK, repository
  tooling, and the deployment distributions are affected consumers
- Governing decisions:
  [Studio ADR-011](../../apps/studio/docs/adr/011-rust-backend-and-single-origin-studio.md)
  and [Studio ADR-012](../../apps/studio/docs/adr/012-studio-authentication.md),
  both accepted on 2026-10-03. They own the architectural decisions below;
  this plan owns sequencing, evidence, and status

## Purpose

Replace the Python/FastAPI Studio backend with a Rust service, serve the Studio
UI from that same service, and give the CLI a browser sign-in.

The intended result is a Studio that uses far less memory, runs as two
containers instead of three, and needs fewer settings to deploy, while keeping
its telemetry, storage, proto, and SDK-facing HTTP contracts.

This is not a one-to-one port. Where the Python structure exists to work around
the language, its bindings, or its frameworks, the Rust backend uses the
simpler native shape. Every such change is listed here so none arrives as a
surprise after implementation.

The full port proceeds only after a small measured slice is compared with the
unchanged Python backend on the supported resource profile.

## Evidence that motivates the work

- Backend peak sampled working set under load is 320–351 MiB against a 450 MiB
  limit. In the same runs ingestion peaks at 35–51 MiB against 350 MiB. See
  [performance mechanics](evidence/studio-performance-mechanics-2026-09-07/README.md)
  and [metadata extraction](evidence/studio-metadata-extraction-2026-09-07/README.md).
- Those backend figures include file cache and native Arrow allocations. The
  September runs do not isolate the interpreter's share or record an idle
  baseline. Work package 2 measured both; see
  [the measurement slice evidence](evidence/studio-backend-rust-2026-10-03/README.md).
- Ingestion already runs the proposed runtime and HTTP stack (Tokio, Tonic,
  Hyper). It measured 15.4–15.6 MiB RSS in the reconnect soak and 21.7–24.1 MiB
  peak under mixed authorization load
  ([Studio ADR-009](../../apps/studio/docs/adr/009-bounded-ingestion-api-key-validation.md),
  [authorization performance plan](STUDIO_INGESTION_API_KEY_AUTHORIZATION_PERFORMANCE.md)).
- Size of the port: 16,338 non-test Python lines, about 5,600 of them evidence
  and diagnostics assembly; 35 test files with 8,775 lines; an HTTP surface of
  36 paths, 41 operations, and 89 component schemas.

## Scope lock

### In scope

- A Rust backend with the same role as today: one process serving the HTTP API
  and the internal gRPC service, over the same on-disk span layout.
- Fresh `junjo.db` and `metadata.db`. There is no upgrade path and no data
  preservation.
- The backend serves the existing React build. The frontend container, CORS,
  and the frontend and backend URL settings are removed.
- Every API route lives under `/api/v1`. SDK-facing paths do not change.
- One unified HTTP error body, with the matching frontend change.
- A browser sign-in for the CLI, built after cutover.
- Everything the cutover touches: Compose, both deployment distributions, the
  release contract, license inventory, CI, repository tooling, skills,
  `AGENTS.md`, public docs, and ADR wording.

### Out of scope

Each item was evaluated on 2026-10-03 and is not part of this plan.

| Idea | Reason |
| --- | --- |
| One binary for backend and ingestion | Ingestion backpressure reads process memory ([ingestion ADR-001](../../apps/studio/ingestion/adr/001-segmented-wal-architecture.md)). Query memory in the same process would trigger ingest rejections. |
| Ingestion validates API keys locally | Explicitly rejected by Studio ADR-009. |
| One Cargo workspace and lockfile shared with ingestion | Forces an Arrow upgrade onto the ingestion hot path and breaks the one-lockfile-per-deployable boundary rule. |
| Ingestion writes per-file summaries at flush | Changes the ingestion hot path and a cross-service contract. Follow-on roadmap, only if indexing still dominates after the port. |
| Server-side rendering | The UI is behind a sign-in and keeps its state in the client. It would add a runtime without a payoff. |
| Remote MCP endpoint and OAuth 2.1 | Its own roadmap after this plan. See "Follow-on roadmaps". |
| Changing query semantics, API-key or token storage, or password hashing | Not required by the port. |

## Decisions already made

Maintainer decisions, 2026-10-03.

1. **No data preservation.** Fresh databases, and every user signs in again.
2. **HTTP contract.** SDK-facing paths, every status code, and every success
   payload stay as they are. Browser-facing routes that sit at the root today
   move under `/api/v1`. Every error body becomes `{code, message}`, the shape
   evaluation conflicts and the SDK already use.
3. **One origin.** The backend serves the existing React build as static files
   on its existing port. This is not server-side rendering.
4. **Sessions.** `tower-sessions` with a server-side store in `junjo.db` and
   sliding 30-day expiry, renewed at most once per day. Both cookie secrets are
   removed.
5. **Automation credentials.** Scoped developer access tokens stay the single
   credential for the CLI, the SDK, and later MCP. The CLI keeps working from
   its environment variable exactly as today, which gates cutover. A browser
   sign-in for the CLI is added after cutover, and it stores its credential in
   a private file in the user's configuration directory.
6. **Database layer.** `rusqlite`, SQL-first. No ORM and no code-generated
   schema.
7. **Schema ownership.** One desired-state SQL file per database and no
   migration files until the product commits to preserving data. At that point
   migrations are generated from the schema file's diff, not hand-written.
8. **Stack.** Tokio, axum, Tonic, and DataFusion are kept after an evaluation
   of lower-resource alternatives. See "Package selection".
9. **Defaults.** axum's 2 MB request-body limit is kept, email addresses are
   lowercased, and audit logging is one event per action.
10. **Continue, with the measured build settings.** Decided at the gate after
    work package 2. Release builds use link-time optimization. The system
    allocator is kept and the `mimalloc` option is removed. DataFusion's
    runtime caches keep their upstream defaults, and the runtime keeps its
    default worker count. Parquet filter pushdown stayed off until work
    package 9 measured it with a filtered-query workload, and was turned on
    from that measurement on 2026-10-04.

## Target architecture

### Process and runtime

- One release binary. Listeners stay separate: HTTP on 26154 and internal gRPC
  on 50053, so the internal port is never published.
- One Tokio multi-thread runtime sized to the available cores.
- One dedicated OS thread for the metadata indexer.
- One shutdown signal. Listeners drain, the indexer stops between files, both
  databases checkpoint their WAL, and the process exits non-zero if any
  long-lived task ends unexpectedly.

### Crate layout

A Cargo workspace owned by the backend, with one lockfile and two crates.

- `evidence`: a pure library with no I/O dependencies. Payload parsing, Store
  reconstruction, Agent and Workflow diagnostics, trace evidence assembly, and
  the telemetry scalar rules.
- `server`: the binary. HTTP, gRPC, SQLite, the indexer, and DataFusion.

The split lets the compiler enforce that evidence logic performs no I/O, and
lets its fixture tests build and run without compiling DataFusion.

During the port the workspace lived in `apps/studio/backend-rs`. It moved to
`apps/studio/backend` when the Python backend was deleted, so the paths that
Compose, the validators, and CI use stay stable.

### One origin for the UI and the API

- The backend serves the built React app from a directory in its image. The
  React app itself does not change.
- Routing rule: `/api/v1` is the API, `/health` is the liveness check, and
  every other GET returns the app, either a static file or `index.html`. An
  unknown path under `/api` returns a JSON 404.
- Static files are compressed once when the image is built. Hashed assets are
  served with long-lived cache headers and `index.html` is never cached.
- The frontend calls the API with same-origin relative URLs. The runtime
  `config.js`, the `API_HOST` setting, the startup script, and nginx are
  removed.
- In development the Vite dev server stays on 26151 and proxies `/api` and
  `/health` to the backend. The browser is same-origin in both modes, so the
  backend carries no CORS code.
- The session cookie is host-only, `HttpOnly`, `SameSite=Strict`, and `Secure`
  in production.
- The backend no longer needs to know its own public URLs. The public
  ingestion URL stays, because the UI shows it in SDK setup instructions.

### API paths

The React app owns `/`, `/sign-in`, `/sign-out`, and `/users` as page routes.
Those collide with today's root-level API routes once both share an origin.

| Today | After |
| --- | --- |
| `GET /` returning service information | Removed. `/` serves the UI |
| `GET /health` | Unchanged |
| `/sign-in`, `/sign-out`, `/auth-test` | `/api/v1/sign-in`, `/api/v1/sign-out`, `/api/v1/auth-test` |
| `/users` and its sub-routes | `/api/v1/users` and the same sub-routes |
| `/api_keys` | `/api/v1/api-keys` |
| `/api/admin/flush-wal` | `/api/v1/admin/flush-wal` |
| `/api/config` | `/api/v1/config`, without the frontend and backend URL fields |
| Everything already under `/api/v1` | Unchanged |

The SDK uses only `/health` and routes already under `/api/v1`, so it is not
affected. The moved routes take explicit operation identifiers in the style
the newer routes already use; frontend mocks that reference the old generated
names are updated.

### HTTP boundary

- Handlers are thin: extract, call one feature function, map the result.
- Feature modules keep their current names. A separate service layer exists
  only where there is logic to hold.
- Request types deserialize into validated domain types, so invalid values
  cannot reach feature code. These carry over the current key, name, record
  identifier, and JSON size rules.
- One error type maps to a status and a `{code, message}` body. Existing
  conflict codes are preserved. Extra fields such as `missing_scopes` and
  `match_count` remain alongside the two common fields.
- Request validation failures and invalid cursors remain 422. Studio ADR-007's
  rule that 422 belongs only to caller validation is unchanged.
- An unhandled panic becomes a 500 with the same body shape.
- OpenAPI is generated from the Rust types and routes with `utoipa`, exported
  by a subcommand of the binary into `backend/openapi.json`, and copied to the
  frontend by the existing workflow.

### Browser sessions and credentials

- `tower-sessions` owns session identifiers, cookie attributes, and expiry.
  The store is a small adapter over the `junjo.db` connections.
- Sign-in verifies the password, rotates the session identifier, and binds the
  user. Sign-out ends that session only. Today it ends every session for the
  user through the `updated_at` revision workaround, which is removed.
- Activity renews the session, written at most once per day per session.
  `tower-sessions` extends expiry only when a session is saved, and saving on
  every request would turn every authenticated read into a SQLite write.
- Passwords stay on bcrypt at cost 12. Length is validated at 8 to 72 bytes,
  bcrypt's real input limit. Today a longer password fails with 400 or 500.
- Email addresses are validated and lowercased at the boundary.
- Developer access tokens, ingestion API keys, and the internal gRPC token keep
  their formats, scopes, storage, and failure semantics. Bearer credentials
  take precedence over the session on token-protected routes, as today.
- One audit event per mutating action, emitted where the action is authorized.
  Today the same action is logged at the service and repository layers.

### CLI browser sign-in

Built after cutover, in work package 10. The flow follows the steps, names, and
outcome codes of the OAuth device authorization grant (RFC 8628), carried in
Studio's own JSON and error conventions. It is the pattern `gh auth login`
uses.

1. `junjo auth login` asks Studio to start a sign-in and receives a short user
   code and a long device code.
2. The CLI prints the code, opens the Studio approval page, and starts polling.
   It derives the page address from its configured Studio origin.
3. The user, signed in to Studio in the browser, confirms that the code and
   the requested scopes match the terminal, and approves or denies.
4. Approval mints an ordinary developer access token bound to the approving
   user. The next poll returns it once.
5. The CLI stores the token for that Studio origin and uses it from then on.

- `junjo auth logout` revokes the token and deletes the stored copy.
  `junjo auth status` reports the origin, where the credential comes from, and
  whether Studio accepts it.
- The environment variable keeps precedence over a stored credential, so
  automation, CI, and coding agents behave exactly as today.
- The token appears in the Developer Access Tokens page and can be revoked
  there like any other.
- The CLI stores the credential in a private file in the user's configuration
  directory. This adds no SDK dependency.
- The CLI still never accepts a Studio password, and ingestion API keys stay
  separate.
- Pending sign-ins expire after a short time and are single-use. Approval
  requires an authenticated browser session.

### SQLite ownership

Each database has exactly one writer connection and one reader connection,
each on its own thread.

| Database | Writer | Reader |
| --- | --- | --- |
| `junjo.db` | Request path, through `tokio-rusqlite` | Request path, through `tokio-rusqlite` |
| `metadata.db` | Owned by the indexer thread, synchronous | Request path, through `tokio-rusqlite` |

- The writer connection is the write-serialization boundary that Studio
  ADR-010 requires. Connection pooling and cross-connection busy handling
  inside the process go away.
- A write transaction is one closure that runs to completion on the database
  thread. It never holds SQLite's write lock across an `await`.
- Four connections in total keeps page-cache memory fixed and predictable, as
  ingestion ADR-002 requires.
- Existing PRAGMA settings carry over unchanged and are then measured.

### Schema ownership

- `schema/junjo.sql` and `schema/metadata.sql` are the only schema sources.
  Tables are `STRICT`. The 46 CHECK constraints and the existing indexes carry
  over.
- The binary creates a missing database from its schema file and stamps a
  schema version.
- On a version mismatch, `junjo.db` refuses to start with a message that names
  the data-volume reset procedure. `metadata.db` is deleted and rebuilt from
  Parquet by the indexer, because it is derived data.
- The schema file is the review surface: every schema change is a diff of
  that one file. Tests apply it to an empty database and prepare every
  repository SQL statement against it.
- One type owns the stored and serialized timestamp format, which stays at
  whole seconds in UTC.
- `metadata.db` drops four indexes that duplicate a primary-key prefix.

### Metadata indexer

- A synchronous loop on its own thread: scan, compare with indexed and failed
  paths, then for each new file read the five metadata columns in streaming
  batches and write the summaries in one transaction.
- Memory follows the batch size and the distinct trace set, not the file size.
- The flush endpoint asks the indexer thread to run now and waits for the
  result, so indexing keeps a single owner.
- Startup reconciliation uses the same scan rules as the indexer.
- One classifier decides whether a span is an LLM, Workflow, or Agent span. The
  indexer and the hot-tier check share it. Today they apply slightly different
  rules for the GenAI attributes; the string rule is the one kept.

### Query engine

Native DataFusion with the same SQL semantics: tier deduplication with cold
over hot, the attribute prefilter with an exact post-filter, ordering, and the
existing file-count bounds.

- One process-wide DataFusion runtime built from the existing `JUNJO_DF_*`
  settings, and one lightweight session per request. The spill pool then
  bounds all concurrent queries together. Today each query gets its own pool.
- Multi-file tables are registered natively. The per-file tables joined with
  `UNION ALL` and the PyArrow materializing fallbacks are not ported.
- Values are bound as query parameters instead of escaped into SQL text.
- Filters are applied while Parquet is decoded, with filter reordering: the
  filter's columns are decoded first and the others only for matching rows.
  The Python backend decoded every row and filtered afterwards. Work package 9
  measured the change before it was adopted.
- Service discovery runs one query over recent-cold and hot data, as the
  September evidence recommended.
- A listing removes cross-tier duplicates among the newest page of each tier,
  with the cold copy winning. The Python backend, and this backend until
  2026-10-04, numbered every matching span of every file whenever a hot
  snapshot existed. Ingestion ADR-002 records the change and its measurement.
- A query that fails after ingestion replaced or removed the hot snapshot it
  was given asks ingestion again and runs once more. The Python backend ran
  one query at a time and never met that. Ingestion ADR-002 records it.
- The LLM listing also classifies the flushed files the index does not hold
  yet, for its candidate traces only, and asks ingestion a second time before
  it does. The Python backend, and this backend until 2026-10-04, classified
  only the hot snapshot, so a flushed trace left the Traces page's default
  view until its file was indexed. Ingestion ADR-002 records the change and
  the cost of the second request.
- Single-span lookup filters by span identifier in the query.
- The four stored JSON columns are validated and passed through as raw JSON on
  the raw span endpoints. They are parsed only where evidence logic inspects
  them.
- The internal token and the `PrepareHotSnapshot` bridge behave as today,
  including cold-only degradation when the snapshot call fails.

### Evidence logic

- Pure functions over parsed spans, ported with the same rules and diagnostic
  codes.
- Strict payload JSON is one explicit scanner that owns the interoperable JSON
  rules: duplicate names, nesting depth, unsafe integers, and invalid Unicode.
  `serde_json` defaults differ from the Python parser on each of these.
- Exact float round-tripping is enabled, because canonical hashes depend on it.
- Values compare the way producers compare them: numbers by value, and
  booleans equal to 0 and 1. Producers compute Store patches with that rule,
  so replay must use it or it would report differences they never emitted.
- JSON Patch replay is a small RFC 6902 implementation owned by the crate. The
  published crate compares the `test` operation strictly, which the RFC and
  the producers do not.
- Object members keep their emitted order.

The port differs from the Python behavior in these deliberate ways.

- Malformed evidence that ended a Python request with an unhandled error now
  becomes a diagnostic. Examples are a patch path through a missing member, a
  non-text value where a set lookup expected text, and a sequence count large
  enough to exhaust memory.
- Messages that quoted a Python `repr` or a library's exception text have new
  wording. Codes and paths are unchanged.
- A reference-mode payload that also carries inline content is reported as
  `invalid_payload_slot`. Python reported `nonportable_scalar_text`, a code
  about text encoding.
- A `move` into the moved value's own child is rejected under an array parent
  as well as an object parent, as RFC 6902 requires.
- A trace diagnostic names its owner span only when that span ID is valid.
- Text that is not Unicode scalar values cannot reach span fields, because a
  Rust string cannot hold it. The strict payload scanner still detects it
  inside payload JSON, where it can occur.

### Internal gRPC

- Tonic serves `ValidateApiKey` with a constant-time token check and the same
  `UNAUTHENTICATED` and `UNAVAILABLE` outcomes.
- One lazy, long-lived channel to ingestion replaces the cached client with
  manual reset. The existing 30-second call deadline is kept.
- Proto code is generated at build time from `apps/studio/proto`. No generated
  code is checked in.

### Configuration and logging

- Configuration is read from the process environment only and fails fast with
  a clear message, following ingestion's convention.
- Kept: `JUNJO_ENV`, `JUNJO_INTERNAL_GRPC_TOKEN`, `JUNJO_PROD_INGESTION_URL`,
  `PORT`, `GRPC_PORT`, `JUNJO_LOG_LEVEL`, `JUNJO_LOG_FORMAT`, the database and
  Parquet paths, `INGESTION_HOST`, `INGESTION_PORT`, the indexer settings, and
  every `JUNJO_DF_*` setting.
- Removed: `JUNJO_SESSION_SECRET`, `JUNJO_SECURE_COOKIE_KEY`,
  `JUNJO_PROD_FRONTEND_URL`, `JUNJO_PROD_BACKEND_URL`, `JUNJO_ALLOW_ORIGINS`,
  `RUN_MIGRATIONS`, and `.env` file discovery inside the binary. The two
  `MALLOC_*` settings stay, because the system allocator was chosen and was
  measured with them.
- Required production settings drop from seven to three: the environment, the
  internal token, and the ingestion URL.
- Structured JSON logs through `tracing`, as in ingestion.

### Build and deployment

- The backend Dockerfile follows ingestion's structure, with one added stage
  that builds the frontend. The production image holds the binary, the built
  UI, and both third-party license inventories.
- Studio releases two images. The main image is published to a new repository,
  `mdrideout/junjo-ai-studio-app`, because it is now the Studio application with
  its UI and API. The bare product name is left free, and `-aio` is reserved
  for a possible future all-in-one image. Ingestion stays `mdrideout/junjo-ai-studio-ingestion`.
  Maintainer decision, 2026-10-03.
- The `junjo-ai-studio-backend` and `junjo-ai-studio-frontend` repositories
  are retired and left frozen at the last Python release, as the
  `junjo-server-*` repositories were. A deployment that still follows their
  floating tags keeps working instead of being pulled across the breaking
  release.
- In the distributions the services are named `junjo-ai-studio-app` and
  `junjo-ai-studio-ingestion`. Inside the repository the directory, the root
  Compose service, and the release-contract key stay `backend`.
- The frontend keeps its own lockfile, tests, and lint. Its container exists
  only as the development Vite server.
- Ports: Studio UI and API on 26154, OTLP ingestion on 26155, the Vite dev
  server on 26151. Port 26153 is retired.
- Production needs one hostname for Studio and one for ingestion.
- No entrypoint script and no init wrapper in production. The binary applies
  its schema and handles termination signals itself.
- Memory limits in Compose and the distributions are not changed by this plan.
  Lowering them is a separate decision after measurement.

## Removed, not ported

- Alembic, its configuration, `entrypoint.sh`, and `RUN_MIGRATIONS`.
- SQLAlchemy models, the connection pool, and SQLAlchemy instrumentation.
- The nginx image and configuration, the frontend startup script, and the
  runtime `config.js`.
- CORS handling and the same-site check for frontend and backend URLs.
- Checked-in generated proto code, its generation scripts, and the two proto
  staleness workflows.
- Unused metadata helpers: time-range file lookup, unbounded file listing,
  per-file indexed check, LLM trace listing, retention cleanup, rebuild,
  vacuum, and index statistics.
- The PyArrow fallback paths and the per-file `UNION ALL` registration.
- The session revision check and the one-second `updated_at` adjustment.
- Fixed-port gRPC tests and the interactive port prompt in the test runner.
- Version strings repeated in source. The binary reports its Cargo version.

## Package selection

Versions were verified on crates.io on 2026-10-03. The measurement slice
compiles and runs with the selections it uses.

| Responsibility | Selection | Notes |
| --- | --- | --- |
| Toolchain | Rust 1.99.0, edition 2024 | Pinned in the workspace and the builder image. The local default toolchain is 1.85. |
| Async runtime | `tokio` 1.53 | Required by DataFusion, Hyper, `tokio-rusqlite`, and `tower-sessions`. |
| HTTP | `axum` 0.8.9, `tower-http` 0.7.1 | A thin layer over the Hyper and Tower stack that Tonic already brings. `tower-http` also serves the static UI. |
| gRPC | `tonic` 0.14.6, `prost` 0.14.4 | Same as ingestion. |
| SQLite | `rusqlite` 0.40.2 bundled, `tokio-rusqlite` 0.8.0 | `sqlx` 0.9 cannot be linked beside this version. |
| Query engine | `datafusion` 55.1.0, features `parquet` and `sql` | Arrow and Parquet 59.3.0 through DataFusion's re-exports. Feature set confirmed by the measurement slice. |
| Sessions | `tower-sessions` 0.15.0 with our own store | No published store fits these versions. `axum-login` is not used. |
| OpenAPI | `utoipa` 6.0.0, `utoipa-axum` 0.3.0 | 6.0.0 was published on 2026-09-22. |
| Passwords | `bcrypt` 0.19.3 | Argon2id costs about 19 MiB per hash. |
| Evidence | `serde_json` with `preserve_order`, `serde_jcs` 0.2.0, `sha2` 0.11, `indexmap` 2 | Canonical JSON, structural hashes, and insertion-ordered indexes. `json-patch` is not used; see "Evidence logic". |
| Validation | `email_address` 0.2.9 | Email addresses. |
| Identifiers and tokens | `nanoid` 0.5, `base64` 0.23, `subtle` 2.6 | Existing formats. |
| Logging and errors | `tracing`, `tracing-subscriber`, `thiserror`, `anyhow` | Same as ingestion. |
| Allocator | System | Chosen by measurement. `mimalloc` used about 50 MiB more memory with no CPU gain. |

Removed from the earlier candidate: `axum-extra` private cookies,
`rusqlite_migration`, `url`, `psl`, and the separate `parquet` declaration.

### Evaluation of lower-resource alternatives

The runtime and framework are not where the backend's resources go. They cost
a few MiB and microseconds per request, and ingestion's measurements on the
same stack confirm it. Request time is spent in SQLite, DataFusion, and JSON.

| Layer | Alternatives considered | Outcome |
| --- | --- | --- |
| Runtime | `monoio`, `glommio`, `compio`, `smol` | Not usable as a replacement: the selected libraries require Tokio. `monoio` and `glommio` last shipped in 2024. |
| HTTP | Hyper alone, `actix-web`, `xitca-web`, `ntex` | No measurable saving. `actix-web` would add a second HTTP stack beside Tonic's. The benchmark leaders have very small adoption. |
| gRPC | `grpcio` | Last shipped in August 2023. |
| SQLite | `sqlx`, `diesel`, Turso | `rusqlite` is the thinnest binding. Turso is a pre-1.0 rewrite. |
| JSON | `simd-json`, `sonic-rs` | Not parsing stored JSON at all is the larger win and is already planned. |
| Query engine | DuckDB, direct Parquet reads without an engine | DataFusion is the one heavy dependency. Kept, and its floor is measured before the full port. |

Parquet codecs cannot be trimmed to LZ4 alone. DataFusion's own dependency
enables Parquet's default codecs.

## Parity and test strategy

Three existing artifacts are the parity oracles.

1. **Generated projections.** `backend/tests/generated/agent_semantic_projections.json`
   and `frontend/src/features/workflow-executions/testing/workflow-store-projections.json`
   are produced by the Python assemblers from the shared telemetry fixtures.
   The Rust generators must reproduce both with no semantic difference before
   the Python generators are deleted.
2. **The committed OpenAPI document.** Frontend and SDK contract tests pin
   operation identifiers, component names, parameter constraints, and
   examples. The Rust export is compared with the committed document. The only
   accepted differences are the error schemas, the moved browser-facing
   routes, and the configuration response.
3. **The benchmark harness.** It gains one setting for its two setup paths,
   which move under `/api/v1`. The measured request paths are identical for
   both backends.

Existing tests map to their destinations as follows.

| Existing tests | Lines | Destination |
| --- | ---: | --- |
| Evidence logic: semantic projections, Store reconstruction, trace evidence, Workflow Store diagnostics | 2,038 | `evidence` unit tests and the generated projections |
| HTTP, auth, validation, security, error recovery, settings | 3,999 | `server` in-process router tests with temporary databases |
| Concurrency races | 722 | `server` tests. Idempotency and conflict outcomes stay; pool contention cases have no equivalent with one writer |
| Internal gRPC | 374 | `server` tests on an ephemeral port |
| Query and metadata extraction | 609 | `server` tests over generated Parquet files |
| Cross-service tests that spawn ingestion | 953 | `server` integration tests that spawn the ingestion binary |
| Alembic migration test | 80 | Replaced by the schema creation, version, and statement preparation tests |

## Work packages

Each package is finished and validated before the next one starts.

### 0. Decisions and ADRs

Status: complete, 2026-10-03. The maintainer accepted both ADRs at the gate.
The queued amendments are listed in each ADR and are made at cutover.

- Propose Studio ADR-011, "Rust backend and single-origin Studio": the
  runtime, SQLite ownership, schema ownership, the error body, the API prefix,
  the shared query runtime, and the backend serving the UI.
- Propose Studio ADR-012, "Studio authentication": server-side sessions,
  developer tokens as the single automation credential, the CLI device
  sign-in, and the OAuth 2.1 work deferred to the MCP roadmap. No Studio
  authentication ADR exists today.
- Queue amendments for Studio ADR-006 and root ADR-0001 (two images instead of
  three, and the renamed main image), root ADR-0013 (CLI sign-in and stored
  credential), Studio ADR-007
  (error body), and the wording in Studio ADR-004, ADR-009, ADR-010, and
  ingestion ADR-002 that names Python, FastAPI, Alembic, or Python source
  paths.
- ADR-011 is accepted only with the results of work package 2.

### 1. Baseline

Status: complete, 2026-10-03. Recorded in
[the measurement slice evidence](evidence/studio-backend-rust-2026-10-03/README.md).

- Record the unchanged Python backend on the supported profile with the
  existing harness: idle memory after startup, the mixed run, and the
  index-completion run, in the shapes the September evidence used. Record the
  frontend container's memory alongside.
- Run alternating orders with no concurrent builds or suites.

### 2. Measurement slice

Status: complete, 2026-10-03. The slice was built in `apps/studio/backend-rs`,
now `apps/studio/backend`. Its
results are in
[the measurement slice evidence](evidence/studio-backend-rust-2026-10-03/README.md).
The maintainer decided to continue.

Build only what the harness needs.

- Configuration, startup, schema creation, and `/health`.
- Create-first-user with session, API-key creation, and `ValidateApiKey`.
- The indexer.
- Service discovery and one trace query, including the hot snapshot bridge.

Then measure as described in "Measurement plan and decision gate". The slice
is disposable if the maintainer decides not to continue.

### 3. Evidence crate

Status: complete, 2026-10-03. The crate is `apps/studio/backend/evidence`.

- Both generated projection files are reproduced with no semantic difference:
  40 Agent cases and 7 Workflow Store cases.
- All 41 invalid fixtures produce their declared diagnostic.
- The shared RFC 6902 replay vectors and RFC 8785 fingerprint vectors pass.
- The Python evidence tests are ported, 117 tests in all. Cases that need text
  a Rust string cannot hold are noted where they were dropped.

The Python generators stay until cutover, because the Python tests still read
them.

- Port payload parsing, reconstruction, diagnostics, and trace evidence.
- Reproduce both generated projection files and the invalid-fixture outcomes.

### 4. Remaining HTTP surface

Status: complete, 2026-10-03.

- Every operation is served: span endpoints, execution resolution, the Agent
  execution listing, trace and Attempt evidence, evaluation tokens with the
  scoped access checks, evaluation, sign-in, sign-out, user management, the
  WAL flush, and configuration.
- The exported OpenAPI document matches the committed one apart from the
  accepted differences, and satisfies the SDK contract test's rules for every
  component that test covers.
- The server crate has 213 tests. Eleven run against the real ingestion
  binary, which the first of them builds: flush, the hot snapshot, the
  recent-cold bridge, a query racing a flush, every valid transport fixture
  at each storage stage, and the LLM filter.
- The evaluation routes were also driven by the SDK's own client, and
  compared call for call with the Python backend on one scenario of 139
  calls: no difference in status, success bodies, or conflict bodies.
- One structural test proves that every route outside the five public ones
  refuses a request that carries no credential.

One feature at a time: span endpoints, execution resolution, Agent
diagnostics and trace evidence, evaluation tokens, evaluation, then users,
admin, and configuration. A feature is done when its tests pass and its paths
match the committed OpenAPI document apart from the accepted differences.

The HTTP surface differs from the Python behavior in these deliberate ways,
beyond the changes listed under "Decisions already made".

- A service name in a span route is one path segment. A name that contains a
  slash is sent percent-encoded, as every Studio client already sends it.
  Python also accepted an unencoded slash.
- An `Authorization` header that is not a bearer credential gets one message.
  Python had two, and one of them could not be reached.
- A token expiry is RFC 3339 text with an offset. Python also accepted a Unix
  timestamp number.
- A boolean query flag is `true` or `false`. Python also accepted `1`, `0`,
  `yes`, `no`, `on`, and `off`.
- An inactive user cannot sign in. Python signed the user in and never
  checked the flag.
- The user listing is ordered oldest first. Python had no stated order.
- A failed WAL flush answers with fixed text and logs the cause. Python
  returned the internal error text to the caller. Indexing that fails after a
  successful flush has its own error code.
- Execution resolution reads a span's error type with the evidence crate's
  strict rules. Python accepted any non-empty value.
- The root route that named the service is gone. The UI is served there.
- A path with a trailing slash is not found. FastAPI redirected it.
- A wrong method on a known path answers 405 with the one error body.
- A rejected JSON body says which member is wrong and why, without the
  parser's position in the text. The UI shows that message under forms.
- Evaluation numbers must be JSON integers. Python also accepted `"1"`,
  `1.0`, and `true` for a version or a duration, and `5.0` for a page size.
- Evaluation input JSON is read by `serde_json`. An integer beyond 64 bits
  becomes a float, `-0` is kept as a negative zero, and nesting deeper than
  126 levels is refused; Python kept big integers exact, read `-0` as `0`,
  and nested to 255. `NaN`, `Infinity`, and a lone surrogate are refused as
  invalid, where Python answered 500.
- Binding evidence reports `evidence_already_bound` only for the uniqueness
  violation. Python reported it for every constraint failure there.
- An audit event is written after its action succeeds, with the record's
  identifier. Python wrote it before the action, so a refused request was
  logged as if it had happened.
- In the OpenAPI document, an optional query parameter is optional, not
  nullable; every error response names the one error schema, except that the
  three conflict schemas clients parse keep their names; 401 and 403 are
  documented; and the two unions the evidence types share are named
  components.

The parity audit of 2026-10-04 found these further differences. None changes
what the frontend, the SDK, or the CLI send or receive, and they are kept.

- A JSON body needs the `Content-Type: application/json` header. FastAPI read
  a body that came without it.
- A member repeated in a request body, or a query parameter repeated in a
  URL, is refused. Python used the last one.
- A time bound on the Agent execution listing is RFC 3339 with `Z` or an
  offset written `+HH:MM`. Python also accepted `+HHMM` and a Unix timestamp.
  The UI's own check still passes `+HHMM`, which the backend then refuses.
- A pagination cursor is accepted only in the form Studio issues. Python also
  decoded padded and non-URL-safe base64.
- A bearer credential is trimmed before it is looked up.
- A request with invalid JSON and no credential is 401. Python answered 422,
  because it read the body first.
- `HEAD` on a GET route is answered as GET without a body. FastAPI answered
  405.
- `GET /openapi.json` is not served. The document is exported by the binary
  and committed. With the UI served, that path returns the application.
- Audit events keep their actions and resource types, and their members
  changed: `session_audit_id` replaces `session_id`, details are top-level
  members, and there is no `authenticated_at`, key preview, or token preview.
  Listing keys or tokens writes no event, as "one event per mutating action"
  decided.
- `JUNJO_PROD_INGESTION_URL` is checked whenever it is set, not only in
  production. An empty value means unset for every setting. A boolean setting
  is `true`, `false`, `1`, `0`, `yes`, `no`, `on`, or `off`.
- A canonical evaluation document writes a number between 0.00001 and 0.0001
  in fixed notation, where Python wrote an exponent. The text is one or two
  bytes longer per such number, which matters only at the size limit.
- The indexer takes unindexed files in path order, oldest first. Python took
  them in directory order.

### 5. Contract cutover

Status: complete, 2026-10-03.

- `apps/studio/frontend/backend/openapi.json`, the committed contract, is now
  the Rust backend's export. `backend/scripts/validate_rest_api_contracts.sh`
  regenerates it and runs the frontend contract tests.
- The frontend's 12 calls, its mocks, and its contract tests use the new
  paths, operation identifiers, and error body: 250 tests, lint, and the build
  pass. The SDK's OpenAPI contract test passes against the same file with no
  change to the SDK.
- The provisioning script, the Agent end-to-end validator, the distribution
  smoke test, and their tests use the new paths: 147 tooling tests pass. The
  benchmark harness's two setup paths default to the new routes.
- The live evaluation script no longer counts the signed-out answer of the
  authentication check as a failure. That check now sits under `/api/`, where
  the script treats every failed response as one.

Not changed here, because they describe the Python backend until cutover:
`run-all-tests.sh`, the version-sync scripts, and the CI workflows. The
version-sync check reads the document's `title` keys, which the Rust export
does not have; it is rewritten with the other CI inputs in work package 7.

- Change the three places where the frontend parses error bodies to
  `{code, message}`, and update the affected mocks.
- Move the frontend, the benchmark harness, the frontend end-to-end scripts,
  and the repository tooling to the new paths. The tooling includes local
  provisioning, the Agent and evaluation end-to-end validators, the
  distribution smoke test, and the runtime and deployment validators.
- Export OpenAPI from Rust. Run the frontend contract tests and the SDK
  OpenAPI contract test against it.

### 6. One origin

Status: complete, 2026-10-03.

- The backend serves the build in the directory `JUNJO_UI_DIR` names. A
  directory without `index.html` stops startup. Without the variable the
  process serves the API only, which is how it runs behind the Vite server.
- Files under `/assets/` are cached for a year as immutable. Every other
  file, `index.html` included, is revalidated on each use. A `.br` or `.gz`
  sibling is sent to a browser that accepts it.
- A missing file under `/assets/` is not found. Answering it with the app, as
  nginx did, would have a browser keep HTML under a script's name for a year.
- The API prefix is `/api/`, with the slash. The app has a page at
  `/api-keys`, so a rule on `/api` alone would send that page to the API. The
  Vite proxy uses the same prefix, and so must any reverse-proxy rule.
- The frontend calls the API with relative URLs. `config.js`, the API host
  setting, `nginx.conf`, `prod-startup.sh`, and the frontend image's nginx
  stage are gone. The Vite server proxies `/api/` and `/health` to
  `JUNJO_DEV_BACKEND_URL`, by default `http://localhost:26154`.
- Checked live: the built UI was loaded from the Rust backend on one port
  with a fresh database, through first-user setup, a refused password, deep
  links, the users page, and sign-out. The backend has 223 tests and the
  frontend 250.

Left for work package 7, because they describe images and Compose: the
repository validator now fails on the frontend Dockerfile, which no longer
has a production stage; Compose still builds that stage; and the end-to-end
scripts still take separate frontend and backend URLs.

- Serve the built UI from the backend with the routing rule above.
- Switch the frontend to same-origin URLs, add the Vite development proxy, and
  remove the runtime configuration, the startup script, and nginx.
- Point the frontend tests at the same-origin base.

### 7. Deployables and the release contract

Status: complete, 2026-10-03, apart from the two checks that only GitHub can
run. They are listed at the end of this section.

The removal of the Python backend and the move of the workspace to
`apps/studio/backend` were brought forward from work package 8 to the start of
this one. Compose, the validators, the release contract, and CI all name the
backend by its directory, so doing the move first let each of them be changed
once, against the final layout.

- **Image.** `backend/Dockerfile` builds the UI, compresses its text files
  once with brotli and gzip, and puts the build, the binary, and the license
  files in the production image. Its development stage runs the API under
  `cargo-watch`, as ingestion's does. `frontend/Dockerfile` keeps only the
  Vite development server.
- **Root Compose.** The backend service builds that image. The frontend
  service is the Vite server only, in the Compose profile `development`, on
  26151. A development stack sets the build target and the profile together;
  the environment template and the root setup script do. The six retired
  settings and port 26153 are gone, and the runtime validator fails if one
  returns.
- **Listener port.** The backend reads `PORT`; the Python image ignored it.
  All three Compose files now pin it, as they already pin the gRPC port, so a
  `PORT` in a shared environment file cannot move the listener off the
  published port. Both validators require the pin.
- **Distributions.** Both run two services, `junjo-ai-studio-app` and
  `junjo-ai-studio-ingestion`, with one Studio hostname and one ingestion
  hostname in the proxy examples. The setup scripts ask for those two
  hostnames and generate one token. The VM/Caddy example application service
  is `example-app`.
- **Release contract.** Two services. The `backend` entry publishes to
  `mdrideout/junjo-ai-studio-app`. The publish matrix, the release validation
  dry builds, and release evidence follow the contract. This is the reviewed
  release-architecture change under Studio ADR-006, which is amended.
- **Licenses.** `licenses/backend-production.json` lists the backend's 293
  crates for both published targets. The application image carries it and the
  frontend inventory. The backend policy lists the 20 license expressions that
  occur. Three were not already allowed for ingestion or the frontend and were
  added: `Apache-2.0 AND MIT`, `Unicode-3.0`, and
  `Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT`. All are permissive.
- **CI.** Backend tests, format, and lint are Rust. REST contract validation
  exports the OpenAPI document, fails if it differs from the committed one,
  and runs the SDK contract test. The telemetry contract workflows run the
  evidence crate's tests as the Studio consumer. Version sync reads the Cargo
  workspace. The two proto staleness workflows and the proto generation
  script are removed.
- **Benchmark harness.** It has its own Python project and lock in
  `ingestion/benchmarks`, and its proxy has a small image of its own that
  generates its proto stubs at build time.
- **End-to-end scripts** take one Studio URL. Local provisioning asks the
  running backend whether it serves the UI and writes the matching browser
  address into the example environment files.

Checked live, with locally built arm64 images, scratch data, and ports of
their own. The root Compose stack itself was first started during the audit
of 2026-10-04, which found and fixed its development build:

- The production image is 65 MB compressed, 277 MB unpacked, and holds the
  96 MB binary, the 8 MB UI build, and the four license files. On a fresh data
  directory
  it serves the UI with brotli, caches files under `/assets/` as immutable,
  answers a missing asset and an unknown `/api/` path with the one error body,
  uses 9 MiB at idle, and stops cleanly on the termination signal.
- The distribution smoke test passes on the VM/Caddy distribution with two
  services: first user and API key on one origin, the example application
  with the published Python SDK 0.69.0, the Agent proof through the SDK and in
  the browser, and the evaluation proof through the SDK and in the browser.

The CI jobs keep their existing time limits. Each new step was timed cold in a
Linux container limited to four CPUs, and scaled by 1.64: the ingestion test
step takes 33 seconds there and 54 seconds in the last CI run.

| Job | Limit | Step, four local CPUs | Projected in CI |
| --- | ---: | ---: | ---: |
| Backend tests, which build ingestion | 15 min | 225 s | about 6 min |
| Backend format and lint | 5 min | 67 s | about 2 min |
| REST contract, the export step | 10 min | 134 s | about 4 min |
| Telemetry contract, the evidence crate | none | 8 s | seconds |

The projections exclude job setup, which installs the pinned toolchain. The
lint job has the least room. The same run passed all 223 server tests and 121
evidence tests on Linux.

Only GitHub can run these, so they are open until the first run there:

- The publish job's 45-minute limit on both architectures. Locally, on arm64
  with 12 CPUs, the image's Rust build takes about 8 minutes 50 seconds
  uncached: about 2 minutes 30 seconds for dependencies and 6 minutes 20
  seconds for the final step with link-time optimization. Ingestion's takes
  59 seconds, and its publish job took about 5 minutes in the last release.
  The amd64 image builds locally under emulation in about 15 minutes, and its
  binary runs.
- The maintainer creates the Docker Hub repository
  `mdrideout/junjo-ai-studio-app` with the contract's immutable-tag rules
  before the first release. The release workflow verifies those rules and
  fails closed without them.

### Catch-up to Studio 0.85.0 and telemetry contract 3

Status: complete, 2026-10-03.

Work packages 1 to 6 were built from repository revision `1faadb5`, Studio
0.84.1. That checkout was seven commits behind the published `master`,
`1b5a798`, which is Studio 0.85.0: telemetry contract 3 and composable
application Stores under root ADR 0016. This was found during work package 7.

- Every file upstream changed was brought into the working tree. Nine files
  had changed on both sides and were merged by hand.
- The Python backend's changes for contract 3 were ported to the evidence
  crate: the active contract version, Store boundaries with transition
  intervals, the Agent application Store, the shared transition log keyed by
  Store identity, Store views by role on each executable, and the Attempt
  manifest and span selection that follow from them.
- The Rust generators reproduce all three of upstream's generated files byte
  for byte: the Agent projections, the Workflow Store projections, and the
  new composable Store trace.
- The exported OpenAPI document has no difference from upstream's 0.85.0
  document beyond the accepted ones.
- The Rust assemblers were also compared with upstream's Python assemblers
  over 11,410 cases built from every fixture and targeted corruptions of
  them. Of 68,460 compared parts, 67,919 were identical including member
  order, 415 differed only in the wording of existing messages, and in 126
  the Python raised an error where the Rust returns evidence.
- The backend has 223 server tests and 121 evidence tests. The frontend has
  257 tests.

The measured baseline in work packages 1 and 2 is the 0.84.1 Python backend.
Work package 9 measures the 0.85.0 Python backend beside the final image.

### 8. Cutover

Status: complete, 2026-10-03. The root ADR 0013 amendment, which describes the
CLI sign-in, was made with work package 10 on 2026-10-04.

- The Python backend is deleted and the workspace is `apps/studio/backend`.
- The benchmark harness has its own Python project.
- `apps/studio/AGENTS.md`, the Studio skills, `TESTING.md`, the READMEs, and
  the proto documents describe the Rust backend. The backend skill is renamed
  `studio-backend-rust`. The Alembic rule is replaced by the schema ownership
  rule.
- The amendments queued by ADR-011 and ADR-012 are made in Studio ADR-004,
  ADR-006, ADR-007, ADR-009, ADR-010, ingestion ADR-002, and root ADR 0001.
  Root ADR 0002 was not on the queued list. It stated which image carries
  which license inventory, which ADR-011 changed, so it carries a dated
  amendment that corrects those facts and nothing else. The maintainer
  approved that amendment on 2026-10-04, and ADR-011 now lists it.
- The public Studio pages, the reset procedure, and both distribution READMEs
  describe two services and one Studio hostname, and tell an operator how to
  move from Studio 0.85.0 or earlier. They name no new version: the
  maintainer chooses it at release preparation.
- The release notes are drafted under "Release notes for the cutover release".

### 9. Final validation

Status: complete, 2026-10-04. Recorded in
[the final image evidence](evidence/studio-backend-rust-final-2026-10-04/README.md).

- The validation routing passes on the final tree: Studio's full test script,
  the deployment distributions with reproducible archives, the distribution
  smoke test, the telemetry contract with its producer and consumer
  conformance, the Python SDK, the frontend, the website, and the repository
  validators. The website's dependency audit fails on three advisories in the
  published lockfile, which this plan does not change.
- The comparison on the final image is against the Studio 0.85.0 Python
  backend, on the same profile and workloads as the first comparison: 29 runs,
  all work completed by both. Backend CPU is 43% lower while ingesting with
  queries and 84% lower in the index-completion workload. Peak sampled backend
  memory is 56–79 MiB against 287–350 MiB. Ingestion is unchanged with
  separate CPU quotas.
- Trace and listing queries were measured for the first time: 58% and 50% less
  backend CPU than Python.

**Decided 2026-10-04: Parquet filter pushdown is on.** Decision 10 kept it
off until a filtered-query workload existed. Measured on that workload,
turning it on halves the Rust backend's CPU again for both trace and listing
queries, with the same results and the same memory. The maintainer turned it
on, with filter reordering. It is not a setting: the measurement-only variable
`JUNJO_DIAGNOSTIC_DF_PUSHDOWN_FILTERS` is removed, and Studio ADR-011 carries
the amendment. An image built with the new default was then measured beside
the earlier image with the variable off and on, and matches the latter; the
evidence records those runs under "Decision and confirmation".

### 10. CLI browser sign-in

Status: complete, 2026-10-04.

- **Backend.** Seven routes and one table, `cli_sign_ins`, with the schema
  version raised to 3. A terminal starts a sign-in and receives a device code
  and a short user code. A signed-in person reads, approves, or denies it by
  that user code. Approval mints an ordinary developer access token with the
  requested name and scopes and no expiry, and the terminal collects it once.
  A developer token can now describe and revoke itself. Starting and
  collecting are public, so the public routes are seven; every other route
  still refuses a request without a credential. A sign-in lives 15 minutes
  and the terminal polls every 5 seconds. The backend has 248 server tests.
- **Frontend.** The approval page at `/cli-sign-in`, behind the sign-in guard.
  It makes the code the most prominent thing, presents the client name as
  something the terminal reported and Studio has not verified, lists the
  requested scopes in the tokens page's words, and tells the person to deny a
  code they did not just see in their own terminal. The frontend has 291
  tests.
- **SDK.** `junjo auth login`, `logout`, and `status`. The credential is
  stored per Studio origin in a private file in the user's configuration
  directory, with no new dependency. `JUNJO_AI_STUDIO_CLI_TOKEN` takes
  precedence, and no file is read when it is set, so automation, CI, and
  coding agents behave as before. The CLI explainer's interface version is 2.
  The SDK has 547 tests.
- **Contracts and decisions.** The OpenAPI document has 41 paths and 47
  operations, and the frontend and SDK contract tests cover the new ones.
  Root ADR 0013 carries the amendment ADR-012 queued.
- **Checked live** on a scratch backend with scratch data: the real CLI
  printed its code, the browser signed in at the deep link and approved it,
  the CLI stored the token without printing it, `status` reported it accepted,
  the environment variable took precedence without the file being read, and
  `logout` revoked and deleted it. No code or token value appears in the
  audit log.

The validation routing was run again on the tree with this work package:
Studio's full test script, the Python SDK's checks and package build, the
tooling tests and repository validators, the website, a secret scan of the
changed files, and the distribution smoke test on rebuilt images all pass.

Known and left as they are:

- An approved sign-in that the terminal never collects leaves its token on
  the tokens page until someone deletes it.
- Starting a sign-in is public and unthrottled. ADR-012 defers throttling.
  Expired sign-ins are deleted when the next one starts.
- At the `debug` log level the request path of the three browser routes
  includes the user code. Device codes and token values are never logged.

### Audit, 2026-10-04

After the decision on filter pushdown, five independent reviews compared the
Rust backend with the Python 0.85.0 backend, for platform behavior, the
telemetry data path, and evaluations with tokens, and reviewed its Rust
conventions and the work it does at runtime. Everything acted on below was
first confirmed by a test, a live run, or the library's source.

**Defects fixed.**

- A damaged cold Parquet file failed the whole query with 500 unless it was
  the first file of the query: registration reads only the first file's
  footer. A failed query is now run once more without the cold files whose
  footers cannot be read, so a query with no damaged file pays nothing.
  Python skipped such a file. The hot snapshot is not handled this way:
  running again without it would answer without the newest spans. "Adopted
  on 2026-10-04" below records what a query does when the snapshot changes
  under it.
- A password of exactly 72 bytes answered 500. bcrypt reads 72 bytes, and the
  hashing call refused them. A password is now 8 to 72 bytes, as ADR-012
  says, and a longer one never verifies.
- An email address was accepted with display text, a domain literal, or a
  domain without a dot. `admin@localhost` was stored, and the Users page then
  refused the whole list. An address is now a plain address with a dotted
  domain, as it was in Python.
- The root Compose development build never started the backend. The
  container that compiles it ran under the 450 MiB production limit, and the
  compiler was killed. The environment template and the setup wizard now
  leave a development build unlimited, the runtime validator requires that of
  the template, and the container warns when it finds a limit. Compiling
  peaked at about 8.5 GiB of charged memory, file cache included, on a
  12-CPU host.
- The development backend took 10 seconds to stop and was killed. It now has
  the signal-forwarding entrypoint and the `init` that ingestion's
  development container has, and stops in under a second with its databases
  checkpointed.
- Deleting an API key whose identifier is not UTF-8 answered with the
  framework's plain text. It now answers with the one error body.
- When a long-lived task ended, the process exited without logging why. The
  cause is now part of the error.
- A line logged while a request is handled now names the request's method
  and path. The startup line names the database paths, the Parquet path, and
  the ingestion address. The first user's audit event names the new address,
  as every other user's does.
- The server declares the `serde_json` feature it uses, and the UI handle is
  shared between requests instead of copied.

**Checked live for the first time:** the root Compose stack in both build
targets, in a scratch project with its own ports and data. The development
build compiles, serves the API directly and through the Vite server, reloads
on a source change in about 18 seconds, and stops cleanly. The production
build serves the UI and the API on one port under the 450 MiB limit and stops
cleanly.

**Validation after the fixes.** Studio's full test script passes: 252 server
tests, 121 evidence tests, 40 ingestion tests, 291 frontend tests with lint
and build, 38 contract tests, and the OpenAPI document check. The 164 tooling
tests, the repository, runtime, deployment, and license validators, and a
secret scan of the changed files pass, and so does the distribution smoke test
on images rebuilt from the tree. The SDK and the website were not changed and
were not run again.

**Findings left as they are.** Each needs a decision or a measurement first,
and all but the last two are in the query shapes and loops both backends
share.

1. A listing sorts every matching span of the files it reads whenever
   unflushed spans exist. The evidence measures it under "Listing queries
   while unflushed spans exist": about 1 s of backend CPU per listing against
   0.016 s, with failures under two concurrent requests. This is the largest
   cost found. Changed on 2026-10-04: see "Adopted on 2026-10-04".
2. Execution resolution reads every executable span in a service's history to
   keep one, and the Agent listing reads every Agent span of the service to
   return one page. Measured on 2026-10-04 with the real frontend while
   spans arrived, and not changed. The evidence records it under "The two
   pages that read a service's history".
   - The Agents page took about 0.9 s at the median with 18 cold files and
     about 2.5 s with 72. It failed 5 of 164 requests at the standard load
     and 44 of 78 at four times the load, each time because the query ran
     out of memory while sorting. The backend peaked at 305–331 MiB where it
     otherwise peaks at about 130.
   - An execution link took about 0.45 s and about 1.15 s, and none failed.
   - Suggested fix for the Agent listing: take the newest Agent spans in
     pages, as the default Traces view takes root spans, and apply the time
     filter in the query. It reads every Agent span today because its
     filters run on assembled evidence.
   - Suggested fix for execution resolution: have the metadata index record
     which files hold each executable's runtime identity, so a link opens
     one or two files. That is a schema change to the index, which is
     rebuildable.
3. A trace or evidence query reads up to 20 recently flushed files for 120
   seconds after a flush, although the index covers them after about 30.
4. The evidence routes hold a trace in three to four forms at once and
   assemble on a runtime worker. No workload measures evidence assembly.
5. The indexer never retries a file whose read failed, even for a transient
   reason, and takes ten files per cycle, oldest first. Changed on
   2026-10-04: a file that failed on I/O or on the index write is tried
   again every cycle, after the files never tried. A file with damaged
   contents is still not retried.
6. A query can still be reading the hot snapshot when another request has
   ingestion rewrite or remove it, and then fails with 500. Python ran one
   query at a time, so it did not happen there. Measured beside live
   ingestion with eight concurrent readers: one failure in about 5,400 trace
   queries in each of two Rust runs, and none in two Python runs. The
   evidence records it under "Queries while spans arrive". This is the one
   place where the port changed what a user can see. Changed on 2026-10-04:
   see "Adopted on 2026-10-04".
7. The run listing issues one outcome query per run. Creating a user hashes
   the password before it checks for a duplicate address.
8. The image runs as root, as ingestion's does. The lint posture is a command
   line and not a workspace table. Nothing ties a schema edit to its version
   constant. Evaluation rows are mapped by column position. The three
   database threads are not among the tasks whose end stops the process.

**Reading these findings against the whole path, 2026-10-04.** The first
write-up of this audit treated the hot tier as a special state. It is the
normal one: ingestion flushes at 25 MB or one hour, so on a live deployment
nearly every query reads a hot snapshot, and findings 1 and 6 are costs of
the main path.

- Freshness is ingestion's to give and the backend's to keep. A span is
  readable at the next snapshot, which ingestion builds at most once a second
  by rewriting its whole log while it holds the log. No change here may add a
  cache in front of that, skip the hot tier, or ask for snapshots more often.
- A hot span and a cold span can be the same span only for about a second
  after a flush, when a reused snapshot is returned beside the new cold file.
  Finding 1 pays for that second on every listing. A change to it must keep
  the cold copy winning and must keep both tiers in every query.
- Finding 3 saves work only between the indexer's cycle and the end of the
  recent-file period after each flush. It is small where flushes are an hour
  apart.
- The indexer's order, oldest first, is the right one for freshness: a file
  that has left ingestion's recent list is readable again only once indexed.
  Its cadence trades ingestion throughput on a shared CPU for index
  freshness, and ingestion's recent list covers 20 files for 120 seconds.

**Prototypes measured with the real frontend, 2026-10-04.** The maintainer
asked that every change be tested with queries from the real frontend while
ingestion processes spans at load. Two changes were prototyped in a scratch
copy, behind measurement-only switches, and measured that way. The evidence
records the runs under "Real-world runs".

- **Listing change, for finding 1.** With both tiers present, a listing
  removes cross-tier duplicates among the newest page of each tier, with the
  cold copy winning, instead of among every matching span. Both tiers are
  still read on every query.
- **Snapshot rerun, for finding 6.** When a query fails and ingestion has
  since replaced or removed its hot snapshot, the backend asks ingestion
  again and runs the query once more. It is not run again after a memory
  error.

With four browser tabs and the real SDK beside 1,440,000 spans in 90 seconds,
the tree of that time took about 11 seconds for the Traces list at the 95th
percentile, failed 12 of 1,407 requests, and held the backend at its 450 MiB
limit. With both changes the list took 0.4 seconds, none of 8,376 requests
failed, and the backend peaked at about 115 MiB. In that load every span was
a root span, which is the most expensive data there is for a Traces listing.

**Adopted on 2026-10-04.** The maintainer decided on those runs to bring both
changes into the tree together, to make the test a repository tool, and to
have a fix for the default Traces view prototyped. Ingestion ADR-002 was
amended first and owns the two changes.

- The listing change is in the query engine as prototyped.
- The rerun covers every read of the snapshot: span queries, the services
  listing, and the second read the default Traces view makes. A snapshot that
  ingestion named and that is gone now fails the query, which then asks
  ingestion again. It is no longer left out.
- The test is `real_world.py` in `apps/studio/ingestion/benchmarks`, with a
  browser driver in the frontend's `e2e` directory. That directory's README
  owns the procedure, and the root `AGENTS.md` states the requirement. Its
  load sends traces with one root span and real export times.

The tree's own image was then measured, with the earlier load and with the
tool. The evidence records the runs under "The adopted build".

- With the earlier load the tree behaves as the prototype did: no failed
  request at either load.
- With one root span per 32-span trace the gain is smaller. The tree
  completed about 20% more page loads than the build before the changes,
  failed none of 11,999 requests where 7 of 5,145 had failed, and peaked at
  about 132 MiB against 163. All of those failures were the snapshot changing
  under a query. The rerun removed them, and the listing change is what
  freed the CPU and the memory.

Validation on the tree after the adoption: Studio's full test script passes
with 258 server tests, 121 evidence tests, 40 ingestion tests, 291 frontend
tests with lint and build, 38 contract tests, and the OpenAPI document check.
The 164 tooling tests, the benchmark directory's tests, and the repository,
runtime, and deployment validators pass.

**The default Traces view, changed on 2026-10-04.** The Traces page opens
with its "Has LLM Spans" filter on, and that listing could not see a trace
whose file was flushed but not yet indexed. With real export times the
default view was missing traces in 15% of loads at the standard load and in
38–64% at four times the load. Two variants of a fix were prototyped and
measured, and the evidence records both under "The default Traces view".

- The first has the listing also read the unindexed files, for the candidate
  traces only. It brought the share under 1% and to about 10%, for a default
  view about 40 ms slower at the median.
- The second also asks ingestion again before that read, looks only for the
  candidates the index has not resolved, and reads only spans that start at
  or after the oldest of their root spans. No default view was short at
  either load. In that batch it completed about 9% fewer page loads and
  ingestion used about 10% more CPU.

The maintainer chose the second on those numbers. Ingestion ADR-002 was
amended first and owns the decision, its cost, and the rule that no other
query asks ingestion twice.

The tree's build was then measured in two more batches, one of them
alternating it with the build before the change on a quiet host. The evidence
records them under "The second variant in the tree".

- No default view was short: none of 1,291 loads at the standard load and
  none of 278 at four times the load, where 214 of 1,402 and 131 of 291 were
  short before the change.
- The cost is smaller than the prototype's batch suggested. The tree
  completed about 6% fewer page loads, and the default view took about 500
  ms at the median against about 410 ms. Ingestion's CPU was the same: the
  10% did not recur, and the host was most likely slower during the
  prototype's runs.
- A span was readable about a tenth of a second later at the median in the
  alternating batch. No request failed in any run of the tree.

Validation on the tree after this change: Studio's full test script passes
with 264 server tests, 121 evidence tests, 40 ingestion tests, 291 frontend
tests with lint and build, 38 contract tests, and the OpenAPI document check.

**One more finding from those runs.** A trace detail page answered 404 for a
trace the list had just shown, once in 3,529 loads. It fits a flush and a
snapshot rebuild landing between ingestion's answer and the backend's read.
Both backends have always had that window. Changed on 2026-10-04: a span
query asks ingestion after the index lookup, and a trace query that finds
nothing under a changed snapshot asks again. Ingestion ADR-002 records it.

**Decisions for the maintainer.**

- Whether the application writes a log line per request at the default
  level, as Python and the frontend container did.
- Whether a running Studio serves its OpenAPI document, as Python did at
  `/openapi.json`.
- Whether listing API keys or developer tokens, which returns their values,
  writes an audit event, as it did in Python.

## Measurement plan and decision gate

All runs use the existing supported profile: backend at 0.5 CPU and 450 MiB,
ingestion at 0.5 CPU and 350 MiB, no swap, plus the whole-stack single-CPU
profile. The ingestion binary and the harness are identical across runs.

Report side by side, for Python and Rust:

- completed work: persisted spans, indexed rows, completed queries;
- export and query latency at p95 and p99, and `ValidateApiKey` latency while
  queries run;
- backend and ingestion CPU;
- idle memory, peak working set, and memory-limit events;
- retries and canonical delivery.

Report the Rust floor by layer, with binary size: listeners only, then with
SQLite connections open, then with the DataFusion runtime created, then after
the first query. This shows what DataFusion costs before the full port depends
on it.

Compare these settings one at a time, and adopt none without evidence:

- allocator: system or `mimalloc`;
- DataFusion runtime caches: upstream defaults or disabled;
- Parquet filter pushdown: off, as today, or on;
- link-time optimization: default profile or enabled.

The Rust result includes the DataFusion upgrade from 50.2 to 55.1. The two
effects are separated only if a regression appears, by building the slice
against the older engine.

The slice does not serve the UI. The final-image comparison in work package 9
notes that the Rust image also replaces the frontend container.

This plan sets no pass threshold. Results are presented and the maintainer
decides whether to continue.

The results were recorded on 2026-10-03 in
[the measurement slice evidence](evidence/studio-backend-rust-2026-10-03/README.md).
The maintainer decided to continue and adopted the settings listed as
decision 10. Filter pushdown was the one comparison still open. It was
measured on 2026-10-04 in
[the final image evidence](evidence/studio-backend-rust-final-2026-10-04/README.md),
and the maintainer turned it on the same day.

## Release notes for the cutover release

Draft for the GitHub release that first ships the Rust backend. The maintainer
chooses its version at release preparation; "this release" below stands for
it. Operator procedures are owned by
[the reset procedure](../../apps/studio/deployments/RESET.md) and the public
deployment page, and are linked here, not repeated.

**What this release is.** Studio's backend is rewritten in Rust and now serves
the web UI itself. Studio runs as two containers instead of three, needs three
production settings instead of seven, and uses far less memory: in the
measured comparison its backend peaked at 56–79 MiB where the Python backend
peaked at 287–350 MiB, with 43% less CPU while ingesting. The comparison is in
[the final image evidence](evidence/studio-backend-rust-final-2026-10-04/README.md).

**Before you upgrade.**

- Reset the Studio data directory. Users, API keys, developer tokens,
  evaluation data, and telemetry are not migrated, and a database from Studio
  0.85.0 or earlier is refused at startup. Follow the reset procedure.
- Everyone signs in again.

**Deployment changes.**

- Two containers. The application image is `mdrideout/junjo-ai-studio-app`. It
  serves the UI and the API on port 26154. Ingestion is unchanged.
  `mdrideout/junjo-ai-studio-backend` and `mdrideout/junjo-ai-studio-frontend`
  receive no further releases.
- One hostname for Studio and one for ingestion. The separate API hostname and
  port 26153 are gone. A reverse proxy sends the whole Studio hostname to the
  application container.
- Remove these settings: `JUNJO_SESSION_SECRET`, `JUNJO_SECURE_COOKIE_KEY`,
  `JUNJO_PROD_FRONTEND_URL`, `JUNJO_PROD_BACKEND_URL`, `JUNJO_ALLOW_ORIGINS`,
  and `RUN_MIGRATIONS`. Production needs `JUNJO_ENV`,
  `JUNJO_INTERNAL_GRPC_TOKEN`, and `JUNJO_PROD_INGESTION_URL`.
- The frontend and backend no longer need to share a registrable domain. There
  is one origin.

**Behavior changes.**

- Sign-out ends the session it is used in. It used to end every session of
  that user.
- A password is 8 to 72 bytes. An inactive user cannot sign in.
- Email addresses are stored and compared in lowercase.
- Request bodies over 2 MB are refused. Every documented request is far
  smaller.
- `JUNJO_DF_SPILL_POOL_MB` bounds all concurrent queries together. It used to
  apply to each query.
- The Traces page's default view, with "Has LLM Spans" checked, keeps showing
  new traces after ingestion flushes them. It used to lose the traces of a
  flushed file until that file was indexed, up to about 30 seconds later.
- The application writes no log line per request at the default log level.
  The Python backend and the frontend container each wrote one. A line logged
  while a request is handled names the request's method and path.
- Audit events keep their actions and resource types. `session_audit_id`
  replaces `session_id`, details are top-level members, and listing API keys
  or developer tokens writes no event.

**For API clients.**

- SDK and CLI routes are unchanged, and the published Python SDK works without
  changes.
- Browser-facing routes moved under `/api/v1`: sign-in, sign-out, users, API
  keys, the WAL flush, and configuration. The configuration response no longer
  returns frontend and backend URLs.
- Every error response is `{code, message}`. Errors used to carry a `detail`
  member, which was text for some errors and a list for validation errors.
- A JSON request body needs the `Content-Type: application/json` header.
- `GET /openapi.json` is no longer served by a running Studio. The API
  document is `apps/studio/frontend/backend/openapi.json` in the repository.
- The deliberate differences in request handling are listed under work
  package 4.

## Validation routing

- Studio: the rewritten `run-all-tests.sh`, plus Compose and Docker validation.
- Deployment distributions: Compose rendering, setup-script dry runs, archive
  contents, and mirror equivalence for both.
- Release: the release policy and contract validators, and the tooling tests.
- Shared contracts: regenerate and validate, prove the generated tree is
  unchanged, and run producer and consumer conformance. The consumer side
  becomes the `evidence` crate's fixture tests.
- Python SDK: Ruff, pytest including the OpenAPI contract test, ty, Griffe,
  build, and Twine. Required at cutover because the OpenAPI document changes,
  and again for the CLI sign-in.
- Frontend: tests, lint, build, and the Workflow interaction suite.
- Website: build, documentation assembly, and parity, because the public
  deployment docs change.

## Follow-on roadmaps

Not part of this plan. Each needs its own evidence and blast-radius review.

1. **Remote MCP endpoint and OAuth 2.1.** Local MCP over stdio needs no new
   backend work: it uses the developer token from the environment, as the MCP
   specification directs. A Studio-hosted endpoint needs OAuth 2.1
   authorization-server endpoints, and no maintained Rust server library
   exists for them. This plan keeps one bearer authorizer and one token table,
   and the CLI sign-in follows the same grant vocabulary, so that work can
   mint rows in the same table.
2. **Ingestion writes per-file summaries at flush.**
3. **Generated migrations**, when the product commits to preserving data.

## Completion criteria

- ADR-011 and ADR-012 are accepted, ADR-011 with the measured results
  attached.
- The generated projection files are reproduced by Rust with no semantic
  difference.
- Frontend and SDK contract tests pass against the Rust OpenAPI export.
- Every destination in the test mapping exists and passes.
- The existing CLI and SDK flows pass unchanged against the Rust backend.
- The UI is served by the backend in root Compose and in both distributions.
- The benchmark comparison on the final image is archived, with completed
  work, latency, CPU, and memory reported for both backends.
- Both deployment distributions validate, and the two-image release dry build
  succeeds on both architectures.
- The Python backend, the frontend image, their tooling, and every document
  that describes them are removed or updated.
- CLI browser sign-in works end to end, and the SDK validation passes.
