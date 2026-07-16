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
- 25 validated findings required remediation. Their corrections are
  implemented; L5 has the accepted bounded low-resource authorization
  architecture and completed evidence matrix under Studio ADR-009
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
  Capture the originating conversation ID for each turn and prevent admitted,
  terminal, and error state from mutating another conversation's rendered
  turn list. Make route/sidebar navigation and hook selection obey one explicit
  policy during an in-flight turn. Add a frontend test that starts a turn in A,
  changes the route to B before polling completes, and proves no A turn or
  failure appears in B.
  Validated with an in-flight route-change regression plus frontend lint/build.
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
| H3 | Route and sidebar selection cannot switch the rendered conversation during a turn, and admitted/terminal state retains the originating conversation ID. | Pass |
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
| M11 | Rebuilt frontend dependencies come from the image while the chat-data volume survives `up --build`. | Pass |
| L1 | A path-scoped PR caller runs producer/consumer telemetry conformance before merge; it exposes a stable check for repository branch protection. | Pass |
| L2 | A path-scoped PR caller runs protobuf regeneration/staleness checks for proto, generator, lock, and build-input changes. | Pass |
| L3 | CI and the local Studio gate inspect scoped porcelain status including untracked generated files. | Pass |
| L4 | HTTP lifespan waits for a successful gRPC bind/start, supervises unexpected termination, and owns graceful shutdown. | Pass |
| L5 | Active behavior uses a 10-second fixed positive TTL, 1,024-entry bound, same-key singleflight, a reconnecting shared channel, eight refresh slots, 32 pending-request slots, and a two-second deadline. Median accepted throughput matched the historical warm-cache baseline (504.31 versus 504.28 exports/second) while mixed-query p95 improved to 40.68 from 47.02 ms. The 42-scenario matrix and 60-second/20-restart soak pass; last accepted post-deletion exports remained inside the fixed window. | Pass — ADR-009 Accepted with full evidence |
| L6 | Protoc 30.2 downloads are architecture-selected and checksum-pinned; arm64 and amd64 builder, development, and production targets build. | Pass |
| L7 | Only the root local `.claude` directory is ignored, and repository validation rejects tracked files hidden by ignore rules. | Pass |
| L9 | Only successful health probes are filtered; failed readiness access records remain visible. | Pass |
| L10 | Not-ready health requests intentionally return 503 and ready requests return 204 without an unhandled traceback. | Pass |

H1 remains already fixed in repository history. M12 and L8 remain validated
facts that intentionally require no repository change. O1–O25 remain blocked:
the supplied report did not state those findings, so inventing or guessing at
their content would not be a valid review.

## Final validation evidence

- Studio's full gate passed: 48 backend unit tests, 90 backend integration
  tests, 9 real-gRPC integration tests, 10 and 14 Rust test groups, 217 frontend
  tests, frontend lint/build, 24 contract tests, and a clean proto regeneration.
- Python SDK passed 328 tests, Ruff, ty, the 428-object Griffe public-surface
  check, package build, and Twine validation.
- AI Chat passed 60 backend tests, 23 frontend tests, lint, build, and Compose
  smoke for both synthetic Gemini and Grok modes. The smoke rebuilt dependencies
  while proving its chat-data marker persisted.
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
- Final `git diff --check` passed and the fix plan has no unchecked actionable
  items.
