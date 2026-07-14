# Agent Horizons 1 And 2 Corrective Integration Plan

- Status: Superseded as a completion record; corrective implementation incomplete
- Date: 2026-07-14
- Owners: Junjo platform

## Purpose

Preserve the accepted Agent runtime, telemetry, ingestion, persistence, and
Studio capabilities from Horizons 1 and 2 while correcting implementation
scope that replaced the existing AI Chat product and narrowed Studio's
frontend evidence model.

This document records the earlier corrective scope. Its Studio evidence and
platform-foundation decisions remain valid, but its AI Chat restoration and
completion claims are superseded by the
[AI Chat Product Restoration And Eval-Driven Development Plan](AI_CHAT_PRODUCT_RESTORATION_AND_EVAL_DRIVEN_DEVELOPMENT.md).
Accepted ADRs continue to own architecture and contracts. In particular,
Studio ADR 007 owns the cohesive trace-evidence boundary described below.

## Non-negotiable preservation rules

The corrective implementation must:

- use commit `255f69d` as the pre-Horizon AI Chat product and visual acceptance
  reference without wholesale-resetting the current branch;
- preserve the existing AI Chat user experience, styling, interactions,
  capabilities, provider integrations, and useful Workflow topology unless a
  change is explicitly required by the accepted Turn or Agent contracts;
- preserve clear graph, state, factory, service, domain, adapter, API, and
  frontend component boundaries;
- retain the accepted Agent kernel, telemetry contract version 2, ingestion
  preservation, hot/cold query architecture, Agent file indexing, backend
  integrity verification, Turn persistence, execution correlation, Studio
  resolution, and Compose portability;
- add verified evidence without removing complete raw evidence from frontend
  exploration;
- validate every Python example automatically when shared SDK inputs change;
- avoid compatibility fallbacks, duplicate sources of truth, and broad
  refactors unrelated to these corrections.

## Scope classification

### Retain

- Public Junjo Agent definition, execution, Tool, ModelDriver, result, state,
  failure, cancellation, lifecycle, and composition contracts.
- Workflow and Agent telemetry contract version 2, Store revisions, operation
  sequences, payload modes, loss signals, fixtures, and conformance tests.
- Rust ingestion preservation fields and the existing OTLP -> WAL -> Parquet
  path.
- Existing hot snapshot, cold file, DataFusion, and cold-wins deduplication
  mechanics.
- Agent-aware metadata indexing and large-scale backend filtering.
- Backend-owned contract validation, Store replay, integrity findings, and
  runtime-identity resolution.
- Server-created, schema-versioned Turn objects and durable Workflow/Agent
  execution references.
- Explicit application correlation, optional debug visibility, stable Studio
  resolver links, and the AI Chat Compose stack.

### Correct

- Replace separate raw and semantic detail models with one cohesive
  trace-evidence document for detail and exploration.
- Restore the original AI Chat product surface and functionality.
- Integrate Agent behavior into the restored application at explicit bounded
  points rather than replacing the application with a deterministic demo.
- Restore automatic validation for `getting_started`, `base`, and `ai_chat`.
- Remove completion and merge-ready claims until all corrective exit criteria
  pass.

### Do not change without a newly approved decision

- Studio ingestion transport, authentication, WAL flushing, hot snapshots,
  cold storage, or DataFusion tier precedence.
- Junjo Graph traversal semantics beyond already accepted Horizon 1 changes.
- Website, Studio deployment topology, Docker namespaces, or release authority.
- Unrelated Studio views, AI Chat styling, or example behavior.

## Target Studio evidence architecture

### One cohesive detail document

Detail and exploration clients consume one backend-provided `TraceEvidence`
document. Complete normalized telemetry and generic verified annotations are
two parts of the same evidence document, joined by stable identities.

```text
TraceEvidence
|- spans
|  |- complete attributes and events
|  |- links and resources
|  |- status and timestamps
|  `- all preserved loss counters
|- executablesBySpanId
|- operationsByOwnerRuntimeId
|- storesById
|  `- verified transitions with source event, before, patch, and after
|- parentAndNestedReferences
`- diagnostics
```

The exact public field names are finalized with the OpenAPI schema, but the
ownership and identity relationships above are required.

### Backend responsibilities

The backend owns only authoritative or storage-dependent work:

- authentication and authorization;
- hot/cold selection, deduplication, normalization, and large-scale filtering;
- active telemetry-contract validation;
- executable, operation, Tool, Store, correlation, parent, and nested-boundary
  interpretation;
- Store patch replay and integrity verification;
- missing, conflicting, malformed, and dropped-evidence findings;
- runtime identity resolution to trace/span identity;
- pagination and cross-trace queries.

Verified annotations must remain generic evidence facts. The backend must not
return structures named after cards, tables, tabs, timelines, or any other
specific frontend visualization.

### Frontend responsibilities

The frontend owns presentation and exploration over the cohesive document:

- indexes and selectors derived from stable IDs;
- sorting, filtering, grouping, comparison, and search within the loaded
  trace;
- parent/child and nested-executable traversal;
- Workflow Graphs, Agent timelines, tables, trees, payload viewers, and future
  visualizations;
- selection state and deep-link navigation;
- combining verified state facts with surrounding raw spans;
- direct inspection of every raw attribute, event, link, resource, status, and
  loss counter.

The frontend does not replay Store patches or independently declare telemetry
integrity. It does not need a backend contract change for a new rendering or
selector over facts already present in `TraceEvidence`.

### API surface

- Add one authenticated trace-evidence detail endpoint addressed by trace ID.
- Keep large-scale summary/list queries where backend filtering and pagination
  are required.
- Keep the execution-resolution endpoint because callers may know only a
  service scope, executable type, and runtime ID.
- Keep the existing raw trace endpoint as a low-level observability surface,
  but Studio detail pages use the cohesive trace-evidence response.
- Fold the current Agent-detail and Workflow-Store-detail facts into
  `TraceEvidence`, then remove those dedicated detail contracts rather than
  maintaining competing frontend sources.

## Corrective work packages

### 1. Establish preservation acceptance fixtures

Before changing AI Chat implementation:

- record its pre-Horizon routes, screens, component tree, styles, user flows,
  provider configuration, and runtime behavior from `255f69d`;
- record the create-contact and handle-message Workflow Graphs, including
  concurrency, conditions, and Subflows;
- define browser assertions for chat navigation, contact creation, avatar
  rendering, message bubbles, unread behavior, image display, and the image
  modal;
- define behavioral assertions for general, work, date, and image responses;
- distinguish required product preservation from internal implementation that
  may change for accepted Turn and Agent contracts.

These fixtures are acceptance oracles, not a second runtime implementation.

### 2. Restore complete automatic example validation

Update `python-examples-smoke.yml` so:

- `getting_started`, `base`, and both AI Chat components run automatically;
- changes to shared SDK runtime, the Python workspace, or its lockfile run all
  examples;
- changes isolated to one example run that example's checks;
- SDK publication validates all examples;
- manual dispatch remains available but is not required for normal coverage.

Required checks:

- `getting_started`: exact sync and executable entrypoint;
- `base`: exact sync, import, Graph compilation, and rendering;
- AI Chat backend: exact sync, Ruff, ty, and deterministic tests;
- AI Chat frontend: `npm ci`, tests, lint, and production build;
- AI Chat deployment: Compose model rendering.

Live provider evaluations remain explicitly invoked and credentialed. They do
not replace deterministic example validation.

### 3. Implement cohesive Studio trace evidence

Backend:

- define the typed `TraceEvidence` contract;
- include every normalized raw span field currently stored and returned,
  including resource attributes and all loss counters;
- reuse the existing Agent, Workflow, and Store assemblers to produce generic
  verified annotations keyed by stable IDs;
- assemble every executable in the trace without merging independently owned
  Store or operation evidence;
- preserve partial evidence with diagnostics instead of dropping raw spans;
- expose one detail endpoint and regenerate OpenAPI;
- retain summary/list and resolution endpoints for their separate query roles;
- remove superseded Agent-detail and Workflow-Store-detail endpoints after the
  cohesive consumer is complete.

Frontend:

- define one lossless `TraceEvidence` schema and store;
- preserve every known top-level raw span field instead of allowing schema
  parsing to strip it;
- build reusable indexes for spans, executable owners, operations, Stores,
  correlation, and nested references;
- migrate Workflow detail, Agent detail, and raw trace exploration to the same
  loaded evidence document;
- keep Workflow and Agent feature components responsible for presentation,
  not evidence reconstruction;
- keep deep links based on trace/span/runtime/Store identities;
- prove a new selector and visualization can be added without a backend API
  change.

### 4. Restore the AI Chat user experience

Restore the original presentation and component organization, including:

- routed chat selection;
- `ChatSidebar`, `ChatHeader`, `ChatWindow`, and `ChatForm`;
- original message bubbles and Tailwind styling;
- avatars, new-contact controls, unread state, image bubbles, and fullscreen
  image modal;
- the original visual hierarchy, spacing, colors, and interaction behavior.

Adapt the restored components to the accepted Turn API through focused client
adapters and selectors. Do not redesign the interface around telemetry or
Turn internals.

The diagnostics UX remains an optional compact per-Turn control. When debug
mode is disabled, the application must remain visually equivalent to its
pre-Horizon form.

### 5. Restore AI Chat functionality and provider integrations

Restore:

- contact creation and its Workflow;
- avatar-generation Subflow;
- multiple contacts, chats, memberships, and message history;
- general, work, date, and image response behavior;
- actual image and avatar artifacts;
- the xAI/Grok and other provider integrations used by the original
  capabilities;
- relevant FastAPI and provider telemetry instrumentation;
- background Turn execution and frontend refresh behavior unless an accepted
  Turn invariant requires a documented change.

Keep `ScriptedModelDriver` in Junjo's SDK-owned tests. The application runtime
uses an explicitly selected live provider and has no deterministic demo or
fallback chain.

### 6. Integrate Turn persistence and Agent composition without replacement

Application admission remains responsible for allocating and durably accepting
the server-owned Turn before execution. Terminal reconciliation remains an
application-service responsibility.

The restored handle-message Workflow retains its deterministic shell and
existing specialized behavior:

```text
Application admits Turn
  -> Handle Message Workflow
       -> concurrently load history and contact
       -> assess directive
       -> branch
            -> work response
            -> date response
            -> image response Subflow
            -> general Agent response
       -> persist outcome
  -> application reconciles terminal Turn state and execution references
```

The general response branch is the primary Workflow-to-Agent proof. The
Workflow supplies mandatory contact and recent-history context. The Agent may
use a narrow Tool for older conversation search. It may invoke the existing
structured image Workflow through a Tool for an
open-ended request that reaches the Agent, proving Agent-to-Workflow
composition without creating a duplicate image procedure.

The explicit image branch remains available for requests classified into the
known deterministic path. Specialized work and date behavior remains explicit
rather than being absorbed into one universal Agent.

Turn persistence retains:

- server-created identity and conversation sequence;
- schema-versioned canonical JSON;
- accepted input and lifecycle status;
- context policy identity;
- Workflow and Agent runtime references;
- completed, failed, and cancelled terminal records;
- reload-safe messages and Studio diagnostic links.

### 7. Remove only superseded replacement code

After the restored product and cohesive Studio consumer pass:

- remove the evidence-dashboard AI Chat presentation;
- remove duplicate demo-only conversation or message abstractions with no
  remaining owner;
- remove superseded Studio detail contracts and feature state;
- retain reusable Agent, Turn, correlation, resolution, Compose, test, and
  integration machinery;
- update public docs and examples to show the restored product and actual
  composition topology.

Do not consolidate mechanical files merely for teaching convenience.

## Validation and exit criteria

The corrective work is complete only when all of the following hold.

### AI Chat preservation

- The restored frontend satisfies the recorded visual and interaction
  acceptance fixtures.
- Contact creation, avatars, multiple chats, unread state, messages, images,
  and image modal work.
- General, work, date, and image scenarios preserve their intended behavior.
- Live provider adapters power the real application and live evals; unrelated
  deterministic validation requires no secret.
- Turn identity, persistence, failure/cancellation, correlation, and execution
  references survive application reload.
- Workflow-to-Agent and Agent-to-Workflow composition remain visible in
  telemetry.

### Studio evidence

- One trace-evidence request supplies complete raw evidence and verified
  annotations for raw, Workflow, and Agent detail views.
- No frontend parse step discards stored resource or loss evidence.
- Workflow and Agent views use the same evidence store and identity indexes.
- Backend replay is authoritative; frontend rendering remains flexible.
- Parent, child, Tool, Store, correlation, nested executable, and deep-link
  selectors work without dedicated visualization endpoints.
- Malformed or partial contract evidence remains inspectable and carries
  explicit diagnostics.

### Repository validation

- Python SDK Ruff, pytest, ty, Sphinx, package build, and Twine checks pass.
- Telemetry fixtures regenerate idempotently and contract validation passes.
- Studio backend, ingestion, frontend, OpenAPI, protobuf, Compose, and Docker
  validation pass for every changed area.
- `getting_started`, `base`, and `ai_chat` validation all run and pass.
- The live AI Chat -> ingestion -> storage -> TraceEvidence -> Studio browser
  proof passes and retains evidence artifacts.

## Review and commit sequence

Implement as reviewable commits in this order:

1. restore all-example CI coverage;
2. add the cohesive TraceEvidence contract and backend assembly;
3. migrate Studio frontend detail/exploration to one evidence store;
4. restore the AI Chat frontend and visual acceptance tests;
5. restore AI Chat capabilities and provider adapters;
6. integrate Turn persistence and bounded Agent composition;
7. remove superseded replacement code and synchronize documentation;
8. run and record the complete cross-system validation.

## 2026-07-14 infrastructure validation record

The following foundations were validated on 2026-07-14. This record does not
establish faithful AI Chat product restoration:

- all Python examples run automatically for their own paths and shared SDK
  changes; `getting_started`, `base`, AI Chat Compose rendering, 39 AI Chat
  backend tests, and 18 frontend tests all pass;
- the Python SDK passes lock validation, Ruff, 320 tests, ty, warning-strict
  Sphinx, package build, and Twine validation;
- telemetry contract generation is idempotent and contract validation passes
  across 9 schemas, 6 Workflow producer fixtures, 33 Agent producer fixtures,
  4 Agent consumer fixtures, 41 invalid fixtures, 22 fingerprint vectors, 7
  RFC 6902 vectors, and 575 bounded malformed-scalar mutations;
- Studio passes backend unit, integration, and gRPC suites, 21 ingestion tests,
  195 frontend tests, lint, production build, OpenAPI synchronization, shared
  contract validation, protobuf validation, and current-code Docker builds;
- the original two-panel AI Chat visual shell, reduced contact and image
  Subflow shapes, explicit demo/Gemini/Grok adapters, background Turn
  execution, persistence, debug links, and both composition directions are
  present, but the historical live AI behavior is not restored;
- Docker bind mounts plus polling-backed FastAPI/watchfiles and Vite watchers
  were exercised with real source edits, proving backend reload and frontend
  HMR on ports 26252 and 26251;
- a disposable Studio stack proved HTTP 202 Turn admission, terminal polling,
  fresh SQLite reload, the exact fourteen-span hybrid hierarchy, one lossless
  `TraceEvidence` document, exact resolution of all three executable owners,
  three independent backend-verified Store replays, and browser navigation
  from the stable resolver into Agent and nested Workflow diagnostics.

The Studio and Horizon 1 kernel/evidence validations remain useful. The AI Chat
preservation and eval-driven-development exit criteria do not pass. Production
publication remains the separate cutover gate recorded in the Agent roadmap.
