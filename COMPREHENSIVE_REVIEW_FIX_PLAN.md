# Comprehensive Review Validation and Fix Plan

This document validates the findings explicitly stated in the supplied
"Comprehensive Review: Junjo Monorepo" against the repository checkout below.
It is both an evidence ledger and the remediation plan for findings that are
validated and still require action.

## Review baseline

- Review started: 2026-07-15
- Repository: `/Users/matt/repos/junjo`
- Branch: `master`
- Commit: `390363c` (`fix(studio): avoid false execution pending state`)
- Initial worktree: clean

The supplied report says there are 54 confirmed findings, but its severity
counts total 53 (1 critical + 5 high + 12 medium + 35 low). It provides enough
detail to identify 28 findings: all critical, high, and medium findings, plus
10 selected low findings. The other 25 claimed low findings are not stated and
therefore cannot be validated one by one from the supplied material.

## Outcome summary

- 28 explicitly described findings reviewed
- 25 validated findings required remediation, and all 25 are fully resolved.
  The five bounded residuals reopened by the 2026-07-18 post-release review
  are also complete. L5 remains resolved under Studio ADR-009
- 1 finding was already fixed before this review baseline (H1)
- 2 factual findings require no repository fix (M12 and L8)
- 25 claimed low findings are blocked because their descriptions were omitted

## Disposition vocabulary

- **Validated — fix required:** reproduced or proven in the current checkout
  and needs remediation. It appears in the fix plan.
- **Validated — no fix required:** factually correct but intentional,
  adequately mitigated, or informational.
- **Already fixed:** the reported behavior existed historically or is directly
  addressed in the current checkout.
- **Not reproduced:** the current checkout does not exhibit the reported
  behavior and no sufficient evidence establishes it.
- **Refuted:** current code or a targeted reproduction contradicts the claim.
- **Blocked:** the report does not provide enough information to validate it.

## Finding ledger

### Critical

| ID | Finding | Status | Evidence |
| --- | --- | --- | --- |
| C1 | Observability span REST API has no authentication | **Validated — fix required** | `otel_spans/router.py:23` creates a dependency-free router; all six handlers return repository span data without `CurrentUser`; `main.py:195` mounts it without a dependency. A targeted ASGI request with the repository stubbed returned `200 []` for unauthenticated `GET /api/v1/observability/services`. The VM/Caddy distribution publishes the backend at `api.<domain>`. `test_auth_bypass.py:294-334` does not enumerate an observability route. |

### High

| ID | Finding | Status | Evidence |
| --- | --- | --- | --- |
| H1 | Tracked `ai_chat` code imports untracked `access_log.py` | **Already fixed** | Both `app.py` and `access_log.py` are tracked in the current index, and the worktree was clean before this ledger was created. Commit `45d6339` added `access_log.py`. The report described a transient pre-commit worktree hazard, not a current repository defect. |
| H2 | Studio session cookie is signed but not encrypted because middleware ordering is reversed | **Validated — fix required** | `main.py:168-183` adds `SecureCookiesMiddleware` before `SessionMiddleware`. Starlette inserts newly added middleware outside earlier middleware, so Session is outermost on responses and SecureCookies never sees its `Set-Cookie`. A targeted ASGI endpoint using the actual app produced a `session` cookie whose signed payload base64-decoded to the test email; Fernet rejected the raw cookie. This contradicts `deployment_validation.py`'s encryption claim. |
| H3 | An in-flight `ai_chat` turn can be applied to the wrong conversation | **Validated — fix required** | `useChat.ts:139-141` blocks only the state update performed by `selectConversation`; `App.tsx:47-50` navigates regardless. The route effect at `useChat.ts:107-109` then selects conversation B during conversation A's pending request. `sendTurn` later writes A's admitted/terminal turn to the one global `turns` array at lines 169 and 171, which now renders for B. Existing hook tests do not cover a route change during a turn. |
| H4 | Studio deep links are lost after in-place sign-in | **Validated — fix required** | `AuthGuard.tsx:21-23` renders `SignIn` without changing the requested URL. On success, `SignInForm.tsx:58-62` always navigates to `/api-keys` or `/`, and its authenticated effect at lines 17-21 independently navigates to `/`. This discards `/resolve/executable?...` and other protected deep links, contrary to ADR 0007's authenticated semantic-link flow. Current tests explicitly assert only the dashboard/API-key redirects. |
| H5 | Studio E2E app is pinned to an SDK telemetry contract Studio cannot read | **Validated — fix required** | `e2e_test_apps/app/uv.lock:108-110` resolves bare `junjo` to 0.61.1 while the monorepo SDK is 0.64.0 and Studio consumers select `junjo.executable_runtime_id`. The app also calls removed APIs: `Graph(sink=...)` at `workflows.py:104-107` while 0.64 requires `sinks=[...]`, and `workflow.get_state_json()` at `main.py:85-88` while execution state now comes from `ExecutionResult`/Store. The deployment workflow is path-triggered by this directory but does not run this app; its validation job compiles only the VM demo app. |

### Medium

| ID | Finding | Status | Evidence |
| --- | --- | --- | --- |
| M1 | `RunConcurrent` with empty items can bypass `max_iterations` and spin without yielding | **Validated — fix required** | `workflow.py:434-441` counts only a `RunConcurrent` group's children, so an empty group increments nothing. `RunConcurrent.service()` returns immediately at lines 155-156. An isolated two-empty-group cycle with `max_iterations=2`, a reachable declared sink, and `asyncio.wait_for(..., 0.2)` still occupied the child process after 2 seconds; the parent had to kill it. |
| M2 | Studio internal gRPC plane is unauthenticated | **Validated — fix required** | Backend auth gRPC binds insecurely to `0.0.0.0` with no interceptor (`grpc_server.py:26-34`). Ingestion's `FlushWAL`/`PrepareHotSnapshot` server likewise binds `0.0.0.0` and registers without authentication (`ingestion/src/main.rs:147-159`). All services, Caddy, the sample app, and the browser-facing frontend share one network in VM/Caddy; development docs also allow application containers to join Studio's network. Network reachability alone exposes a key-validity oracle and ingestion control calls. |
| M3 | Internal-auth DB errors become non-retryable `UNAUTHENTICATED`, causing telemetry loss | **Validated — fix required** | `grpc_service.py:44-66` returns `is_valid=False` for every repository exception. Ingestion treats false as `Status::unauthenticated` (`trace_service.rs:62-70`). Backend connection failure is also collapsed to `Ok(false)` in `backend/client.rs:51-57`. Thus transient auth-service/DB outages are indistinguishable from bad credentials to OTLP exporters. |
| M4 | Studio sign-out does not invalidate a captured stateless session cookie | **Validated — fix required** | `sign_out` only clears the response-side session (`auth/router.py:135-152`), while `get_authenticated_user` accepts any still-valid signed cookie and never checks `session_id` server-side. A targeted replay proved the normal client became signed out, but a separately replayed pre-sign-out cookie still restored `userEmail`. The cookie lifetime is 30 days. |
| M5 | OTLP span-kind mapping is off by one and drops `CONSUMER` | **Validated — fix required** | Ingestion persists the raw protobuf enum (`span.kind as i8`), whose values are 0 unspecified, 1 internal, 2 server, 3 client, 4 producer, 5 consumer. `datafusion_query.py:693` instead maps 0 internal through 4 consumer and defaults 5 to internal. Test transport helper `_KIND_TO_INT` repeats the same incorrect zero-based mapping, masking the defect. |
| M6 | Attacker-controlled `nodeRuntimeId` can inject Mermaid syntax | **Validated — fix required** | `JNodeSchema` accepts any string. `JunjoGraph.toMermaid()` interpolates runtime IDs unquoted into node, subgraph, child, and edge grammar (`junjo-graph.ts:89-148`); only labels are escaped. Raw OTLP attributes are evidence, not trusted source code, so a crafted graph snapshot can alter or invalidate the Mermaid program. Mermaid's renderer security mode does not restore graph integrity. |
| M7 | Service names are interpolated into API paths/routes without encoding | **Validated — fix required** | `TracesList.tsx:19-23` and `get-spans-type-workflow.ts:13` build backend paths with raw service names. `AppNamesList.tsx:57-64` and numerous detail links similarly build React routes without encoding. Service names originate in telemetry and may legally contain path/query delimiters, causing route confusion or requests for a different backend path. |
| M8 | Canonical workflow fixtures omit `junjo.workflow.node.count` | **Validated — fix required** | All six `contracts/telemetry/fixtures/workflow/*.json` files omit the attribute. The SDK always sets it on the workflow owner span at `workflow.py:549`; Studio reads it in `WorkflowListItem.tsx:17`; Agent-owned fixtures that embed workflows include it. The contract validator currently does not catch the workflow-fixture omission. |
| M9 | The `stable-releases.json` publish gate is missing from `RELEASE_POLICY.md` | **Validated — fix required** | `python-publish.yml` makes stable website validation a PyPI prerequisite, and `website-ci.yml` invokes `validate_release_manifest.py`, which requires the Python manifest entry to select the exact release tag. `sdks/python/RELEASE_POLICY.md` lists neither the manifest update nor this fail-closed release step. |
| M10 | Docs-only releases can promote stable docs for an SDK version that was never published | **Validated — fix required** | `validate_release_manifest.py:21-22` returns immediately for `docs-release-*`. Stable assembly verifies that manifest tags/versions/refs are internally consistent and exist in Git, but neither it nor `documentation-publish.yml` verifies that each selected component release produced its public artifact. Promotion verifies only that the docs-only GitHub release itself is published. A component tag whose publish job failed can therefore be selected as stable. |
| M11 | `ai_chat`'s `node_modules` volume can hide frontend dependencies from rebuilt images | **Validated — fix required** | `compose.yaml:73-75` bind-mounts the frontend and overlays `/app/node_modules` with a persistent named volume. Docker initializes that volume from the first image, then the volume survives later `up --build` runs and hides the rebuilt image's dependencies. This contradicts README lines 113-116 and the frontend README line 43. |
| M12 | The documented `ai_chat` reset command destroys chat data | **Validated — no fix required** | `docker compose down --volumes` deletes both `ai-chat-data` and the frontend modules volume, so the factual statement is true. However README lines 115-123 explicitly say SQLite and generated images live in `ai-chat-data`, describe the command as an explicit reset of them, and say there are no migrations or seeded contacts. It is not presented as a dependency-refresh command. M11 still needs a non-destructive dependency solution. |

### Low findings explicitly stated in the report

| ID | Finding | Status | Evidence |
| --- | --- | --- | --- |
| L1 | Telemetry-contract staleness checks do not run on pull requests | **Validated — fix required** | `telemetry-contract.yml` has only `push`, `workflow_dispatch`, and `workflow_call` triggers. It is called by Studio release validation, not by a PR workflow. The PR `platform-gate.yml` runs repository/tooling invariants only. A cross-component contract change can therefore merge before this conformance suite runs on `master`. |
| L2 | Studio proto-staleness checks do not run on pull requests | **Validated — fix required** | `studio-proto-staleness-check.yml` likewise has no `pull_request` trigger and is called only by Studio release validation. None of the four PR-triggered workflows calls it. Stale generated protobufs can merge and be discovered only after merge/release rehearsal. |
| L3 | Proto staleness uses `git diff` and misses untracked generated stubs | **Validated — fix required** | The CI workflow checks only `git diff --exit-code`; `run-all-tests.sh:126-133` and the pre-commit helper use the same tracked-diff assumption. `git diff` does not report a newly generated untracked module, so adding a new proto file/service can pass while omitting its generated stub. |
| L4 | Internal-auth gRPC server startup is fire-and-forget, allowing partial backend startup | **Validated — fix required** | Studio lifespan creates `start_grpc_server_background()` as a task and immediately yields (`main.py:111-116`). It never waits for bind/start success or monitors task completion during runtime. A port conflict or later server failure leaves HTTP serving while ingestion auth is unavailable; the exception is observed only, at best, during shutdown. |
| L5 | Revoked API keys may authenticate ingestion for the cache TTL | **Validated — fix required** | Ingestion caches only successful validations for 600 seconds (`server/auth.rs:10-26`) and returns true on a hit without consulting backend. Backend deletion only removes the SQLite row; there is no cache-eviction/revocation RPC. A key deleted just after validation remains accepted for up to ten minutes. |
| L6 | Ingestion Docker build uses an unpinned Debian `protobuf-compiler` despite version policy | **Validated — fix required** | Both builder and development stages install the moving distro package (`ingestion/Dockerfile:4-8,46-49`). `PROTO_VERSIONS.md:14,35-36,82-83` requires exactly system protoc 30.2; CI and the backend image install 30.2 explicitly. The ingestion image therefore does not implement its stated build contract. |
| L7 | `.gitignore`'s `.claude` rule conflicts with a tracked file | **Validated — fix required** | Root `.gitignore:180` uses unanchored `.claude`, which matches every such directory. `git ls-files -ci --exclude-standard` reports tracked `apps/studio/.claude/commands/prepare.md` as ignored. The rule also intentionally matches local root `.claude/settings.local.json`, so it needs scoping rather than deletion. |
| L8 | Untracked pre-monorepo root `src/`, `tests/`, or `dist/` directories remain on disk | **Validated — no fix required** | All three directories exist locally and contain old wheels plus Python bytecode/egg metadata; timestamps and history predate or straddle consolidation. They are ignored and absent from the index, and the review baseline was otherwise clean. They are local build residue, not repository state. They were deliberately not deleted because unrelated local files belong to the user. |
| L9 | `access_log` documentation says successful health probes are suppressed, but all probes are suppressed | **Validated — fix required** | `HealthCheckAccessLogFilter` claims to suppress successful probes but checks only `arguments[2] == /api/healthz`; it never inspects status at argument 4. A constructed Uvicorn 500 health record was suppressed (`filter=False`). The sole test covers only a 204 probe. This hides failed readiness requests from the access log. |
| L10 | `/api/healthz` returns an unhandled 500 when not ready and lacks a regression test | **Validated — fix required** | The route calls `_application()`, which raises bare `RuntimeError` when lifespan state is absent. A targeted ASGI request without lifespan, with exception propagation disabled to match production, returned `500 Internal Server Error`. Existing tests cover only the initialized 204 case. A readiness miss should be an intentional 503 without an application traceback. |

### Findings omitted from the supplied report

| ID | Finding | Status | Evidence |
| --- | --- | --- | --- |
| O1–O25 | Remaining claimed low-severity findings | Blocked | No finding text, file reference, or reproduction was supplied. |

## Fix plan

Only findings with a final disposition of **Validated — fix required** are
listed here. Ordering will prioritize security/data loss, then correctness,
release integrity, and maintainability. Each item will include the required
code, tests, documentation/ADR impact, and validation commands after review.

### P0 — security boundary

- [x] **C1: Require authentication on the entire observability router.**
  Add one router-level `get_authenticated_user` dependency so every present and
  future `/api/v1/observability/*` handler is protected. Extend the auth-bypass
  suite with representative collection and item routes (ideally enumerate all
  six current endpoints), assert unauthenticated requests return 401 before
  repository access, and retain authenticated success coverage.
  Validated with unauthenticated collection/item requests returning 401.
- [x] **H2: Put cookie encryption outside session signing.** Register
  `SecureCookiesMiddleware` after `SessionMiddleware`, correct the misleading
  order comments, and add a runtime regression test proving the emitted cookie
  does not disclose a base64-decoded session payload and can be decrypted by
  the configured encryption layer. Keep the deployment log's encryption claim
  only once the test passes.
  Validated by decrypting the emitted browser cookie with the configured Fernet
  key and recovering the signed session payload only after decryption.

### P1 — user-visible correctness and compatibility

- [x] **H3: Keep turn results scoped to their originating conversation.**
  Make the route the sole selected-conversation identity and give a keyed
  conversation pane ownership of its Turns, failures, composer, loading, and
  polling. Navigating or creating a contact unmounts only the old browser pane;
  its server-admitted Turn continues durably and reloads from authoritative
  history on return. A different conversation remains independently usable.
  Validated with cross-conversation concurrency, route/remount, draft-reset,
  polling-cleanup, full frontend test, lint, and production-build coverage.
- [x] **H4: Preserve protected deep links across in-place authentication.**
  Distinguish a guarded in-place sign-in from the standalone `/sign-in` route.
  For the guarded case, let the authentication state reveal the already
  requested route instead of navigating to a default. Add router-level tests
  for `/resolve/executable` (including its query string) and another protected
  detail route; retain intentional default navigation for a direct sign-in.
  Validated both semantic resolver query strings and workflow detail routes;
  the standalone sign-in redirect behavior remains covered.
- [x] **H5: Restore the Studio E2E app as a current contract consumer.** Pin or
  source the supported SDK version explicitly, update `Graph` construction and
  execution-result state access, regenerate its lockfile, and add a CI smoke
  that imports/builds and executes at least one workflow using the exact locked
  environment. The smoke must assert current identity attributes are emitted
  and consumable by Studio, not merely byte-compile the app.
  Validated in its frozen 0.64.0 environment by executing a workflow and
  asserting current runtime identity and node-count telemetry attributes.

### P1 — runtime safety and data integrity

- [x] **M1: Count every graph executable toward the loop bound.** Count the
  `RunConcurrent` wrapper on every visit (while retaining child counts as
  separate execution evidence), or reject empty groups during construction.
  Add a valid retry-cycle test with empty groups that deterministically reaches
  `max_iterations`, plus an event-loop responsiveness/cancellation regression.
  Implemented the allowed construction-time rejection: empty concurrent groups
  now fail before graph execution, so the zero-await cycle cannot be formed.
- [x] **M3: Preserve the invalid-key versus unavailable distinction end to
  end.** Return a gRPC `UNAVAILABLE`/equivalent status for repository and auth
  service failures, reserve `is_valid=false` for an authoritative miss, and
  map transport failures in ingestion to a retryable OTLP status. Test DB
  failure, backend connection failure, genuinely invalid key, and exporter
  retry behavior.
  Validated authoritative misses, repository failures, backend connection
  failures, and retryable ingestion status mapping.
- [x] **M4: Make session IDs revocable.** Use the existing persisted user
  revision as a session epoch, require it in `get_authenticated_user`, and
  advance it before clearing the cookie on sign-out. This avoids a schema
  migration while invalidating every captured cookie for that user.
  Validated old-cookie replay, normal logout, deleted users, and two concurrent
  sessions; the existing signed-cookie `max_age` remains the expiry bound.
- [x] **M5: Use the canonical OTLP `SpanKind` enum values.** Map 0 through 5
  explicitly, decide how `UNSPECIFIED` is represented in the REST contract,
  remove the incorrect zero-based test helper, and cover every enum value from
  OTLP input through Parquet and REST output.
  Validated for all six enum values plus unknown-value fallback.
- [x] **M6: Never use telemetry IDs as Mermaid identifiers.** Generate a local
  safe Mermaid ID for each graph node and maintain a map back to the opaque
  runtime ID for selection. Validate structural references against that map
  and add malicious newline/directive/quote/punctuation cases to renderer and
  DOM-selection tests.
  Validated with malicious grammar input, real Mermaid rendering, and DOM selection.
- [x] **M7: Centralize URL construction for opaque path segments.** Encode
  service names and every telemetry-derived route segment exactly once in
  shared API/route builders; decode only through router/backend path handling.
  Inventory all workflow, trace, prompt-playground, and breadcrumb links and
  test names containing slash, percent, question mark, hash, spaces, and
  Unicode.
  Validated shared builders across UI/API routes, including an authenticated
  backend round-trip for slash, percent, spaces, and Unicode.
- [x] **M8: Bring canonical Workflow fixtures back in sync.** Add the exact
  terminal node count to all six Workflow owner spans, make the compatibility
  validator require it where the SDK contract guarantees it, and run fixture
  generation/determinism plus SDK producer and Studio consumer conformance.
  Validated all six fixtures with the contract validator; full producer and
  consumer suites remain in final validation.

### P2 — internal boundary, release, and development reliability

- [x] **M2: Protect the internal gRPC control plane.** Define the internal
  trust contract, then isolate backend and ingestion control ports on a private
  network that excludes frontend, proxy, and application containers and/or
  authenticate calls with workload credentials (mTLS where supported). Apply
  the same contract to both backend key validation and ingestion control RPCs,
  update every canonical deployment, and add unauthorized/authorized RPC tests.
  Implemented one required high-entropy workload credential on backend auth and
  ingestion control RPCs, withheld it from frontend/proxy/app containers, and
  validated authorized and unauthenticated calls across Python and Rust.
- [x] **M9: Document the stable documentation release gate.** Add the exact
  `stable-releases.json` preparation step, tag/ref invariants, local validation
  command, and ordering relative to GitHub release publication to the Python
  release policy. Keep ADR 0009 as strategy and the release policy as the
  operator runbook.
  Added the exact manifest invariants, validation command, and pre-publication
  ordering to the Python release runbook.
- [x] **M10: Prove docs-only selections are actually released.** During
  docs-only stable validation, verify every manifest component against
  authoritative publication evidence: published GitHub release plus the
  installable PyPI version for Python, and the Studio release's immutable image
  or release-evidence contract. Fail before production-branch promotion and
  add negative tests for tag-only and failed-publish cases.
  Docs-only validation now requires published GitHub releases, Python files on
  PyPI, and Studio `RELEASE_EVIDENCE.json`; positive and negative cases pass.
- [x] **M11: Make frontend dependency refresh deterministic without deleting
  chat data.** Remove the persistent modules overlay or key/recreate only that
  volume when `package-lock.json` changes. Update both READMEs with a verified
  non-destructive dependency-refresh command and add a Compose smoke that
  changes a locked dependency while preserving `ai-chat-data`.
  Removed the `node_modules` overlay, restricted the source bind mount to
  `frontend/src`, and validated `up --build` plus installed dependencies while
  a marker in `ai-chat-data` survived the rebuild.

### P3 — CI and operational hardening

- [x] **L1: Run telemetry contract conformance before merge.** Add a
  path-scoped PR caller/trigger for `telemetry-contract.yml`, include all
  producer/consumer/fixture paths, and make its aggregate result a required
  check. Keep the push/release callers as defense in depth.
  Added a path-scoped pull-request caller for the reusable conformance workflow.
- [x] **L2: Run protobuf staleness before merge.** Add a path-scoped PR
  caller/trigger for the reusable proto workflow and require it when proto,
  generators, locks, or build inputs change.
  Added a path-scoped pull-request caller for the reusable proto workflow.
- [x] **L3: Detect tracked and untracked generated output.** After generation,
  fail on `git status --porcelain --untracked-files=all` scoped to proto sources
  and generated directories (or intent-to-add before diff). Apply the same
  logic to CI and `run-all-tests.sh`; test a newly generated file case.
  CI and the local Studio gate now inspect scoped porcelain status, including
  untracked files; the workflow contract regression passes.
- [x] **L4: Supervise internal-auth gRPC startup and lifetime.** Make lifespan
  wait for a positive server-start handshake before yielding and fail FastAPI
  startup if bind/start fails. Supervise unexpected task completion during
  runtime and add port-conflict/server-failure tests plus graceful shutdown.
  HTTP lifespan now waits for successful bind/start, supervises unexpected
  termination, and owns graceful shutdown; bind and awaited-start tests pass.
- [x] **L5: Enforce an explicit API-key revocation bound.** Choose and document
  the required revocation latency, then add cache invalidation on deletion (or
  remove/shorten positive caching enough to meet that bound). Test a warm-cache
  key immediately before and after deletion. Coordinate any new internal RPC
  with M2's authenticated control-plane work.
  The implemented design is governed by
  [Studio ADR-009](apps/studio/docs/adr/009-bounded-ingestion-api-key-validation.md)
  and the
  [authorization performance plan](docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_PERFORMANCE.md):
  one reconnecting multiplexed channel, a 10-second fixed-TTL positive-only
  cache, same-key refresh coalescing, 1,024-entry capacity, eight backend
  refreshes, 32 pending decoded requests, and a two-second deadline. Invalid
  and unavailable outcomes are never cached, saturation remains retryable, and
  focused tests, historical comparisons, the 42-scenario one-vCPU matrix, and
  the 60-second/20-restart soak pass. ADR-009 is Accepted; the original implicit
  ten-minute revocation behavior is removed and explicitly bounded.
- [x] **L6: Install the locked protoc in ingestion images.** Reuse the
  architecture-aware 30.2 download pattern used by the backend/CI, verify
  `protoc --version` during both builder stages, and pin/check downloaded
  artifacts. Validate production and development image builds on supported
  architectures.
  Both builder stages now checksum and install protoc 30.2 for arm64 and amd64.
  Native and emulated builder, development, and final production images build.
- [x] **L7: Scope the local Claude ignore rule.** Change the repository-root
  local-settings ignore to an anchored rule such as `/.claude/` (or a precise
  file pattern) so the tracked Studio command directory is not classified as
  ignored. Add a repository invariant using `git ls-files -ci`.
  The ignore is root-anchored and repository validation now rejects any tracked
  file matched by standard ignore rules.
- [x] **L9: Preserve failed health access logs.** Suppress only successful
  `/api/healthz` statuses and allow 4xx/5xx records. Cover malformed log records,
  204, and 500 in the filter test.
  Validated with successful and failed health-record filter cases.
- [x] **L10: Make readiness failure explicit.** Return a small 503 response
  when `chat_application` is unavailable, without routing through the generic
  runtime failure path. Test the pre-lifespan/not-ready 503, ready 204, and the
  L9 logging behavior together.
  Validated with pre-lifespan 503 and initialized-lifespan 204 tests.

## Review notes

- The report repeats its title, TLDR, and critical finding verbatim. The
  duplicate is treated as one finding, C1.
- The report's working-tree note describes a different checkout
  (`codex/retire-sphinx-docs` with uncommitted changes). This review validates
  product findings against the baseline above; checkout-specific statements
  are recorded only where they affect a finding such as H1 or L8.
- That working-tree note is no longer current: `master` is clean apart from
  this ledger, `codex/retire-sphinx-docs` points at the same commit, and the
  Studio correction (`390363c`/`3e99439`), Sphinx retirement (`94392ad`), and
  AI Chat health/access-log work (`45d6339`) are separate commits. The requested
  split and addition of `access_log.py` have already occurred.
- During review, one shell loop used zsh's special `path` variable and
  temporarily removed `git` from that subprocess's command search path; a
  subsequent read-only command reran the checks with a neutral variable name.
  Another loop used zsh's read-only `status` variable; it was rerun with
  `finding_state`. Neither command changed repository files.
- The first AI Chat frontend verification used Studio's `test:run` script
  name. AI Chat defines `test`; the corrected command was
  `npm test -- --run src/hooks/useChat.test.ts` and all seven hook tests passed.

## Final finding-by-finding implementation audit

Every item below was re-read against its original reproduction, its final diff,
and a focused or owning-component validation. "Pass" means the implementation
removes the reported behavior and the regression evidence exercises that
specific boundary.

| ID | Final review | Result |
| --- | --- | --- |
| C1 | Router-level auth protects present and future observability handlers; unauthenticated collection and item probes stop before repository access. | Pass |
| H2 | SecureCookies is outermost and limited to the session cookie; the browser value must be Fernet-decrypted before its signed session payload is readable. | Pass |
| H3 | The URL is the only selected-conversation identity. A keyed pane owns one conversation's Turns, failures, composer, and polling; navigation cleans up the old pane while the durable server Turn continues and reloads on return. | Pass |
| H4 | Guarded sign-in reveals the existing protected location, including resolver query strings; standalone `/sign-in` keeps its intentional default navigation. | Pass |
| H5 | The frozen E2E environment uses SDK 0.64.0 APIs, executes a real workflow, and asserts current runtime identity and node-count telemetry. | Pass |
| M1 | Empty `RunConcurrent` groups are rejected at construction, eliminating the no-await, zero-counter cycle. | Pass |
| M2 | A required high-entropy workload token protects backend auth and ingestion control RPCs and is withheld from frontend, proxy, and app containers. | Pass |
| M3 | Authoritative misses remain `is_valid=false`; DB, connection, and RPC failures propagate as retryable `UNAVAILABLE`. | Pass |
| M4 | Cookies carry the persisted user revision and sign-out advances it before cookie clearing, so captured and concurrent old sessions fail replay. | Pass |
| M5 | All canonical OTLP kind values 0 through 5 survive ingestion and REST mapping, with a defined unspecified fallback. | Pass |
| M6 | Mermaid uses generated local identifiers and maps DOM selection back to opaque runtime IDs; telemetry cannot inject grammar. | Pass |
| M7 | One shared builder encodes every opaque segment exactly once and rejects missing mandatory segments rather than shifting them. | Pass |
| M8 | All six workflow fixtures contain the exact successful executable count, and validation recomputes it from the span hierarchy. | Pass |
| M9 | The Python runbook now includes manifest invariants, the exact validation command, and pre-publication ordering. | Pass |
| M10 | Docs-only promotion requires published releases, PyPI files for Python, and immutable Studio release evidence; tag-only selections fail. | Pass |
| M11 | Compose mounts only source, asserts `/app/node_modules` is not mounted, validates the image-owned dependency tree, and proves chat storage survives rebuild without claiming a synthetic dependency mutation. | Pass |
| L1 | A path-scoped PR caller runs producer/consumer telemetry conformance before merge; it exposes a stable check for repository branch protection. | Pass |
| L2 | A path-scoped PR caller runs protobuf regeneration/staleness checks for proto, generator, lock, and build-input changes. | Pass |
| L3 | CI, the full local gate, and the installed pre-commit helper inspect scoped porcelain status including untracked generated stubs; the helper's Ruff path is independently rooted at Studio. | Pass |
| L4 | HTTP startup waits for gRPC, unexpected later termination or supervisor failure sends `SIGTERM` through Uvicorn's graceful shutdown path, and intentional shutdown cancels supervision before stopping gRPC. | Pass |
| L5 | Active behavior uses a 10-second fixed positive TTL, 1,024-entry bound, same-key singleflight, a reconnecting shared channel, eight refresh slots, 32 pending-request slots, and a two-second deadline. Median accepted throughput matched the historical warm-cache baseline (504.31 versus 504.28 exports/second) while mixed-query p95 improved to 40.68 from 47.02 ms. The 42-scenario matrix and 60-second/20-restart soak pass; last accepted post-deletion exports remained inside the fixed window. | Pass — ADR-009 Accepted with full evidence |
| L6 | Every Rust-building CI path uses protoc 30.2; both backend-workflow jobs verify the pinned release checksum and exact compiler version before building. | Pass |
| L7 | Only the root local `.claude` directory is ignored, and repository validation rejects tracked files hidden by ignore rules. | Pass |
| L9 | Only successful health probes are filtered; failed readiness access records remain visible. | Pass |
| L10 | Not-ready health requests intentionally return 503 and ready requests return 204 without an unhandled traceback. | Pass |

H1 remains already fixed in repository history. M12 and L8 remain validated
facts that intentionally require no repository change. O1–O25 remain blocked:
the supplied report did not state those findings, so inventing or guessing at
their content would not be a valid review.

## Post-release residual implementation plan

- Review date: 2026-07-18
- Baseline: `master` at `6f516ca` (`studio-v0.82.0`), clean and synchronized
  with `origin/master`
- Original scope: H3, M11, L3, L4, and L6 residuals plus the two verification
  gaps called out by the follow-up review. All scoped residuals are complete
- Change policy: preserve current runtime, persistence, telemetry, UI, and
  deployment architectures; make the smallest complete correction for each
  demonstrated behavior

### Proportionality disposition

| Order | Item | Disposition | Required scope |
| --- | --- | --- | --- |
| ✓ | L4 runtime gRPC supervision | **Completed 2026-07-18** | One explicit process-shutdown signal path and focused lifecycle tests |
| ✓ | H3 conversation state ownership | **Completed 2026-07-18** | The route is the selection source and a keyed pane owns that conversation's Turns, errors, form, and polling |
| ✓ | L6 Rust CI compiler drift | **Completed 2026-07-18** | Both CI install blocks use checksum-verified protoc 30.2 |
| ✓ | L3 pre-commit untracked output | **Completed 2026-07-18** | The installed helper uses the accepted scoped porcelain check and its contract test covers it |
| ✓ | M11 stale frontend README | **Completed with H3** | The README now distinguishes the mounted `src` tree from image-owned dependencies and configuration |
| ✓ | M11 Compose smoke overclaim | **Completed 2026-07-18** | The smoke asserts no dependency mount, keeps `npm ls`, preserves chat data, and narrows its message |
| — | L5 authorization performance | No action | ADR-009 and its measured evidence remain authoritative |
| — | Broad `junjo.*` reconciliation gap | No action without a concrete mismatch | Existing explicit producer, transport, fixture, and consumer contracts remain the boundary |

No item in this plan requires a new ADR. L4 implements the already intended
co-hosted process lifecycle, H3 corrects an example-local React ownership
boundary without changing durable Turn ownership, and L3/L6/M11 are
implementation and evidence alignment.

### Work package 1 — make unexpected internal gRPC termination stop Studio (completed)

**Problem and evidence**

Startup fail-fast is correct: `start_grpc_server()` waits for a successful
bind and start before FastAPI completes lifespan startup. The runtime
supervisor in `apps/studio/backend/app/main.py` later cancels the ASGI lifespan
task if `wait_for_termination()` returns unexpectedly. Under the locked
Uvicorn 0.38.0 implementation, a post-start lifespan failure sets Uvicorn's
lifespan error flag but does not set `Server.should_exit`; the HTTP main loop
continues. A focused local reproduction observed a finalized lifespan and
`lifespan.error_occured=true` while the Uvicorn server task remained active and
`should_exit=false`.

The selected replacement was also feasibility-tested against the same pinned
server: self-sent `SIGTERM` made Uvicorn drain, run the lifespan cleanup, finish
the server process, and then re-raise the signal for process exit (`143`). That
is the exact behavior needed by Tini and Compose's restart policy.

That state is worse than a clean process failure: the lifespan `finally` block
can checkpoint and dispose databases while HTTP continues accepting requests,
and ingestion can no longer refresh API-key authorization.

**Affected surface**

- `apps/studio/backend/app/main.py`: gRPC supervision and lifespan cleanup
- `apps/studio/backend/tests/test_grpc_server_lifecycle.py`: startup coverage
  and the new runtime-supervision coverage
- `apps/studio/backend/Dockerfile`: validation context only; Tini already
  forwards signals and Uvicorn is already the executed child
- canonical Compose and both deployment distributions: validation context
  only; every backend already uses `restart: unless-stopped`

No gRPC protocol, authentication, ingestion, health endpoint, Compose, or
deployment-file change is required.

**Selected solution**

- [x] Replace lifespan-task cancellation with a small, directly testable
  supervisor coroutine that awaits `grpc_server.wait_for_termination()` and,
  only on unexpected return, logs a critical runtime failure and sends
  `SIGTERM` to the current process.
- [x] Keep normal shutdown graceful: the lifespan `finally` block first
  cancels and awaits the supervisor task, then calls `stop_grpc_server()`. A
  normal intentional stop must therefore never reach the self-signal path.
- [x] Let Uvicorn's existing signal handler own HTTP draining and lifespan
  shutdown. Let Tini and the existing Compose restart policy own process
  reaping and restart. Do not call `os._exit`, because that would skip WAL
  checkpointing and database disposal.
- [x] Remove the now-unnecessary captured lifespan task and `shutting_down`
  cancellation state. Keep the supervisor beside the lifespan code rather
  than adding a new lifecycle module.

**Regression evidence**

- [x] Unexpected `wait_for_termination()` completion sends exactly one
  `SIGTERM` to `os.getpid()`.
- [x] Cancelling the supervisor during ordinary lifespan shutdown sends no
  signal and still stops the gRPC server once.
- [x] Existing port-conflict and positive-start tests remain green.
- [x] The focused backend suite proves cleanup still runs through the normal
  lifespan shutdown path; no test should terminate the pytest process itself,
  so process signaling is patched at the unit boundary.

**Implementation result**

The supervisor now signals the current process on both unexpected gRPC
termination and supervision failure. Normal shutdown cancels and awaits the
supervisor before the intentional gRPC stop, so no signal is emitted. Five
focused lifecycle tests, the complete backend gate, and Studio's full gate
pass.

**Rejected expansion**

- Do not introduce a custom Uvicorn launcher merely to expose
  `Server.should_exit` to application code.
- Do not split HTTP and internal gRPC into new containers or processes.
- Do not add a second readiness state or rely on Docker health alone; Compose
  does not restart an otherwise running container merely because it is
  unhealthy.
- Do not add an external supervisor. The supported deployment already has
  Tini plus a restart policy.

### Work package 2 — give conversation state a conventional React owner (completed)

**Problem and design principle**

The bug is not that contact creation, navigation, and Turns overlap. The
backend intentionally owns durable background Turns, rejects only a second
active Turn in the same conversation, and permits work in different
conversations. The frontend should preserve that concurrency.

The current `useChat` hook combines four separate responsibilities:

1. global configuration;
2. the global conversation/contact list;
3. selected-conversation identity, duplicated from the route parameter; and
4. the selected conversation's Turns, errors, form activity, and polling.

Because the hook instance survives route-parameter changes, one `turns` array
and one error state are reused for A, B, and C. Navigation was then blocked to
contain that ownership mistake. Adding identity refs to every callback would
make the code correct but leave a web of synchronization logic.

Use React's normal ownership boundary instead: the URL owns selection, the app
shell owns global data, and a conversation-keyed child owns conversation-local
data. React then destroys the old pane's state when the key changes, so A's
state cannot become C's state.

**Target component and state shape**

```text
App (route + navigation + read markers)
├── useChatShell (config, conversations, contact creation, passive summaries)
├── ChatSidebar
├── ChatHeader
└── ConversationPane key={conversationId}
    ├── useConversationTurns(conversationId)
    ├── conversation-local error
    ├── ChatWindow
    └── ChatForm
```

Affected files are expected to be:

- `sdks/python/examples/ai_chat/frontend/src/App.tsx`
- `hooks/useChat.ts`, replaced by `hooks/useChatShell.ts` and
  `hooks/useConversationTurns.ts`
- focused shell, conversation, and app interaction tests
- `components/ConversationPane.tsx`
- `sdks/python/examples/ai_chat/frontend/README.md`

`ChatSidebar`, `NewContactButton`, the backend API, Turn schema, SQLite
adapter, and ADR 0008 remain unchanged. `ChatForm`, `ChatHeader`, and
`ChatWindow` remain presentational and should need at most prop wiring.

**Selected solution**

- [x] Make `chat_id` from React Router the only selected-conversation source.
  Remove `selectedConversationId` state, the route-to-state synchronization
  effect, `selectConversation()`, and the effect that forces the route back
  while a Turn is sending. Sidebar selection navigates directly.
- [x] Keep one small app-shell hook for global configuration, conversation
  summaries, passive summary refresh, contact creation, and shell-level
  failures. Successful contact creation updates the global list and returns
  the new conversation so `App` can navigate to it.
- [x] Render a top-level `ConversationPane` with `key={chatId}` whenever a
  route conversation exists. The pane receives `conversationId`, configuration,
  and an `onViewed` callback; it owns Turns, loading, submission state,
  polling, and conversation-local failures. The app derives the presentational
  header from the same route identity and global conversation list.
- [x] Put the composer inside the keyed pane. Changing conversations therefore
  resets its draft by React identity rather than an effect or manual reset,
  preventing a draft for A from being submitted to B.
- [x] Make Turn submission a short event operation: submit to the selected
  conversation, place the admitted Turn into that pane's local list, and end
  the submission state. Do not keep the event handler awaiting terminal
  completion.
- [x] Derive the active Turn from the pane's Turn list. An effect polls that
  Turn's server-owned ID every two seconds until terminal. The existing
  ten-second passive history refresh remains responsible for ordinary external
  updates.
- [x] Abort or ignore every conversation effect during cleanup. Changing the
  pane key unmounts A, stops A's browser polling, and makes all late A responses
  irrelevant to C. The already-admitted server Turn continues independently.
- [x] On mounting or returning to a conversation, load its authoritative Turn
  history. If the response contains an admitted or running Turn, the derived
  active-Turn effect resumes polling automatically.
- [x] Disable only the selected conversation's composer while its admission is
  pending or its loaded Turn list contains an active Turn. Navigating to B
  mounts independent B state, so the user may submit B while A continues. The
  backend remains authoritative for its existing one-active-Turn-per-
  conversation invariant.
- [x] Let the existing global conversation-summary refresh discover terminal
  timestamps. Do not couple the unmounted A pane back into shell state merely
  for an eager sidebar timestamp.
- [x] Keep last-read timestamps in `App`; let the mounted pane report its latest
  visible Turn timestamp through the existing app-owned map boundary.
- [x] Update the frontend README to describe background Turns, concurrent
  navigation/contact creation, per-conversation UI ownership, and reload-on-
  return behavior.

**Regression evidence**

- [x] The route parameter alone determines the active sidebar item, header,
  Turn pane, and API conversation ID; there is no mirrored selection state.
- [x] Start A, navigate to B or create C, and prove the new pane renders
  immediately while A's old polling is cleaned up and cannot mutate it.
- [x] Submit a Turn in B while A continues server-side; each request uses its
  own route conversation ID and neither pane displays the other's Turn.
- [x] Return to A, load its persisted admitted/running Turn, resume polling,
  and render its terminal state.
- [x] A late history or Turn response after unmount produces no B/C Turn,
  error, loading, or form-state change.
- [x] Switching conversation keys resets the composer draft.
- [x] Contact creation remains available during a Turn, updates the global
  list, and navigates to the new keyed pane.
- [x] Existing API-schema, admitted/completed/failed Turn, diagnostic-link,
  unread-marker, contact-creation, and restored-surface tests remain green.

**Implementation result**

`App` now reads selection only from React Router and owns only navigation,
global shell data, and read markers. `ConversationPane key={chatId}` owns one
conversation through `useConversationTurns`; its cleanup aborts outstanding
history and active-Turn reads, and late responses are ignored. Turn admission
ends after the durable admitted Turn is stored locally, while a separate effect
polls that Turn to terminal state. The full frontend suite passes 27 tests,
including cross-conversation contact/Turn concurrency, authoritative reload,
active-Turn resumption, draft reset, and both history and Turn-poll cleanup.
Frontend lint and the production TypeScript/Vite build also pass. The real
Compose infrastructure smoke rebuilt the frontend and brought both synthetic
Gemini and Grok configurations to healthy state without provider calls.

**Rejected expansion**

- Do not serialize contact creation, navigation, and Turn execution behind one
  UI lock.
- Do not scatter selected-identity refs and equality checks through every
  asynchronous callback.
- Do not add a client-side per-conversation cache or reducer; component-local
  state plus authoritative reload is sufficient for this example.
- Do not add TanStack Query, SWR, a React Router data-router migration, Redux,
  or another state library for this bounded frontend.
- Do not cancel a server-admitted Turn when its pane unmounts.
- Do not change backend concurrency or durable Turn ownership.

### Work package 3 — compile Rust tests with the locked protoc (completed)

**Problem and surface**

The production ingestion images and proto-staleness workflow use protoc 30.2,
but both Rust-building jobs in
`.github/workflows/studio-backend-tests.yml` install Ubuntu's moving
`protobuf-compiler`. The ingestion-only job compiles the Rust test target with
that compiler, and the backend integration job builds the real ingestion
binary exercised by Python integration tests. This is a test-versus-production
reproducibility gap, not a currently observed wire incompatibility.

**Selected solution**

- [x] Replace both `apt-get install protobuf-compiler` blocks with the existing
  Linux x86_64 protoc 30.2 artifact, pinned to SHA-256
  `327e9397c6fb3ea2a542513a3221334c6f76f7aa524a7d2561142b67b312a01f`.
- [x] Use `curl -fsSLO`, verify the checksum before extraction, install
  `bin/protoc` plus its include tree, remove the archive, and require the exact
  output `libprotoc 30.2` before either job proceeds.
- [x] Keep the two job setup blocks self-contained. Do not add a composite
  action, third-party setup action, or repository installer abstraction for
  two small CI consumers.
- [x] Update `apps/studio/PROTO_VERSIONS.md` so it accurately states that all
  Rust-building CI paths use the locked compiler.

**Regression evidence**

- [x] Add a workflow-contract assertion that the backend/ingestion workflow
  contains the locked version, checksum, and version assertion and no longer
  installs distro `protobuf-compiler`.
- [x] Run `cargo test --locked` and the real-ingestion backend integration
  suite with protoc 30.2.
- [x] Run the existing proto-staleness workflow logic; proto sources and
  generated Python files must remain unchanged.

No Dockerfile or proto-content change is part of this package.

**Implementation result**

Both Rust-building jobs now download and checksum the same protoc 30.2 Linux
x86_64 artifact, install its compiler and include tree, and fail unless the
reported version is exact. An isolated Linux/amd64 build used that archive to
compile ingestion and pass all 37 Rust tests. Studio's full gate regenerated
the Python stubs without producing tracked or untracked changes.

### Work package 4 — make the installed pre-commit hook see untracked stubs (completed)

**Problem and surface**

CI and `apps/studio/run-all-tests.sh` use scoped porcelain status and therefore
see new untracked generated modules. The installed hook still branches on
`git diff --quiet app/proto_gen/`, so a newly generated `*_pb2.py` file alone
does not trigger staging. CI prevents a merge escape, making this a local
developer-workflow defect rather than a release-integrity defect.

The same script contains a directly adjacent path typo:
`run_ruff_check()` refers to undefined `REPO_ROOT` even though the script owns
`STUDIO_ROOT`. It currently continues from the backend directory only because
of prior function side effects. Correcting that one variable is in scope; a
broader hook rewrite is not.

**Selected solution**

- [x] In `apps/studio/scripts/pre-commit.sh`, compute scoped
  `git status --porcelain --untracked-files=all -- app/proto_gen/` after
  generation. If nonempty, stage the directory and report generated changes.
- [x] Change the Ruff directory reference from `REPO_ROOT` to `STUDIO_ROOT` so
  the function does not depend on the previous working directory.
- [x] Extend `ProtoStalenessWorkflowTests` to require the untracked-aware check
  in the pre-commit script as well as CI and the full local gate.
- [x] Correct `apps/studio/PROTO_VERSIONS.md`, which still says CI uses only
  `git diff`, to describe the scoped untracked-aware check.

Do not introduce a hook framework, shared shell library, or generated-output
manifest for this correction.

**Implementation result**

The installed helper now stages scoped tracked or untracked generated output
and runs Ruff from `STUDIO_ROOT` without depending on a previous function's
working directory. Shell syntax and the extended tooling contract pass, and
the full Studio gate confirms clean regeneration.

### Work package 5 — make the AI Chat Compose proof and docs exact (completed)

**Problem and surface**

The M11 runtime fix is sound: Compose mounts only `frontend/src`, dependencies
remain in the rebuilt image, and the `ai-chat-data` volume survives
`up --build`. Two evidence details were identified:

- `frontend/README.md` said the entire frontend directory was bind-mounted;
- the smoke's unchanged `npm ls --all` proves dependency-tree health after a
  rebuild, but not that a deliberately changed lockfile was refreshed.

**Selected solution**

- [x] Update the frontend README to say only `frontend/src` is mounted, source
  edits use HMR, and dependency/configuration changes require an image rebuild.
- [x] In `validate-compose-startup.sh`, inspect the running frontend
  container's mounts and fail if `/app/node_modules` is a mount destination.
  This directly guards against the original volume-shadowing regression.
- [x] Retain post-rebuild `npm ls --all` as proof that the image-owned
  dependency tree is internally consistent.
- [x] Retain the backend data-volume marker as proof that `up --build` does not
  delete chat data.
- [x] Change the success text to state exactly those three facts; do not claim
  that the test mutated or refreshed a dependency version.

**Implementation result**

The smoke now inspects the running container and rejects an
`/app/node_modules` mount, validates the installed dependency tree, and proves
the chat-data marker survives rebuild. Its success text states exactly those
facts. Both synthetic Gemini and Grok configurations pass without provider
calls.

**Rejected expansion**

- Do not edit `package.json` or `package-lock.json` dynamically inside the
  release smoke.
- Do not add a network-dependent temporary package solely to prove Docker
  layer invalidation.
- Do not restore a `node_modules` volume or widen the source bind mount.

### Completed implementation order

1. L4 was implemented and validated independently because it changes Studio
   process lifecycle behavior.
2. H3 and both M11 evidence corrections were completed in the AI Chat example.
3. L6 and L3 were completed together as Studio build/developer-tooling
   consistency work.
4. The ledger was re-read against the final diffs; every residual checkbox and
   audit row now has focused passing evidence.

These packages may be separate commits. None depends on a telemetry contract,
database migration, generated proto change, deployment mirror update, or
version bump.

### Validation matrix

| Package | Focused validation | Owning-area validation |
| --- | --- | --- |
| L4 | `uv run pytest tests/test_grpc_server_lifecycle.py -q` plus the new supervision tests | `apps/studio/backend/scripts/run-backend-tests.sh`; then `apps/studio/run-all-tests.sh` |
| H3 | AI Chat shell-hook, keyed conversation-pane, polling-cleanup, and routing interaction tests | `npm test`, `npm run lint`, and `npm run build` from the AI Chat frontend |
| M11 | Mount-shadow assertion, `npm ls --all`, and chat-data marker in the real Compose stack | `sdks/python/examples/ai_chat/scripts/validate-compose-startup.sh` for Gemini and Grok configuration modes |
| L6 | Exact `protoc --version`, `cargo test --locked`, and real-ingestion backend integration tests | Studio proto-staleness logic and the full Studio gate |
| L3 | Extended workflow-contract test and shell syntax check | All tooling tests, repository invariants, and the full Studio gate |

Final shared checks are `git diff --check`, a clean proto-generation status,
and a clean working tree except for the intended implementation. Because no
telemetry or proto content changes, fixture regeneration and cross-component
contract versioning are explicitly out of scope.

### Release implications

- L4 changes the Studio backend runtime image and should ship in the next
  normal Studio patch or minor release. It does not justify recalling 0.82.0:
  startup failure is already fail-fast, and unexpected post-start server
  termination is a low-frequency path.
- H3 and M11 affect the AI Chat example and its release gate, not the public
  `junjo` wheel API. They can ship with the next normal SDK repository release;
  no SDK API version change is required solely for these fixes.
- L3 and L6 affect local/CI reproducibility only and do not independently
  require a release.
- L5 remains closed. The accepted 10-second fixed positive cache, reusable
  channel, and measured one-vCPU/1GB evidence must not be modified as part of
  these packages.
- The unspecified O1–O25 findings remain blocked until their actual text and
  evidence are supplied.

## Final validation evidence

- Studio's full gate passed: 48 backend unit tests, 90 backend integration
  tests, 9 real-gRPC integration tests, 10 and 14 Rust test groups, 217 frontend
  tests, frontend lint/build, 24 contract tests, and a clean proto regeneration.
- Python SDK passed 328 tests, Ruff, ty, the 428-object Griffe public-surface
  check, package build, and Twine validation.
- AI Chat passed 60 backend tests, 23 frontend tests, lint, build, and Compose
  smoke for both synthetic Gemini and Grok modes. The smoke rebuilt dependencies
  while proving its chat-data marker persisted.
- The post-release H3 implementation passed all 27 AI Chat frontend tests,
  lint, and a production TypeScript/Vite build. Focused coverage proves keyed
  route ownership, cross-conversation concurrency, authoritative remount,
  active-Turn polling resumption, draft reset, and effect cleanup. The real
  Compose smoke also passed for synthetic Gemini and Grok configurations.
- The residual cleanup pass added five focused gRPC lifecycle tests. The full
  Studio gate passed 48 unit, 90 integration, 9 real-gRPC, 37 Rust, 217
  frontend, and 24 REST-contract tests plus lint, builds, and clean proto
  regeneration. An isolated Linux/amd64 build compiled ingestion with the
  checksum-pinned protoc 30.2 archive and passed all 37 Rust tests.
- The revised AI Chat Compose smoke directly proved image-owned dependencies,
  a valid installed dependency tree, and rebuild-persistent chat storage for
  both synthetic provider configurations without provider calls.
- Telemetry contract generation was byte-deterministic; validation passed 9
  schemas, all 6 Workflow fixtures, 33 Agent producer fixtures, 4 Agent consumer
  fixtures, invalid/fingerprint/RFC 6902 vectors, and 575 malformed mutations.
- Website assembly checked 140 source documents. Website install, type/check,
  build, parity validation, link audit, and dependency audit passed (129 pages,
  126 routes, 428 API objects, zero audit vulnerabilities).
- All 117 tooling tests passed. Repository invariants, both Studio deployment
  distributions, development/production runtime overlays, and live stable-docs
  selection `docs-release-20260715.1` validated.
- Frozen Studio E2E workflow smoke passed. Ingestion builder, development, and
  final production images passed for native arm64 and emulated amd64 with
  checksum-verified protoc 30.2.
- Final `git diff --check` passed for the original remediation. All five
  residual IDs reopened by the post-release review are now complete.
