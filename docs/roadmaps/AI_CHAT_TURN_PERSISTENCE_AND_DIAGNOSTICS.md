# AI Chat Turn Persistence And Studio Diagnostics Plan

- Status: Complete; live product and Studio proof recorded in the restoration plan
- Date: 2026-07-14
- Owners: Junjo platform

## Objective

Turn the Horizon 2 AI Chat proof into the first durable application example
that connects one server-owned user action to deterministic Workflow steps,
bounded Agent autonomy, versioned product data, complete telemetry evidence,
and exact Studio diagnostics.

This plan implements [ADR 0007](../adr/0007-execution-correlation-and-studio-resolution.md)
and [ADR 0008](../adr/0008-versioned-application-object-persistence.md).

The Turn, correlation, resolution, and debug mechanics recorded here are
implemented and integrated with Studio's cohesive trace-evidence model. Their
faithful integration into the real AI Chat product remains governed by the
[AI Chat Product Restoration And Eval-Driven Development Plan](AI_CHAT_PRODUCT_RESTORATION_AND_EVAL_DRIVEN_DEVELOPMENT.md).

## Implemented topology

The top-level topology is one deterministic Workflow with bounded Agent
autonomy only in the general-response branch:

```text
HTTP request
  -> ChatApplication durably admits a server-owned Turn and returns HTTP 202
  -> background ChatTurnService execution
  -> Chat Turn Workflow
       -> concurrently load bounded history and contact
       -> assess known message directive
       -> work, date, image Subflow, or general response branch
       -> general branch invokes the AI Chat Agent
            -> optional older-history Tool
            -> optional create-image Tool -> Create Chat Image Workflow
       -> PersistOutcomeNode
  -> ChatTurnService records terminal status and execution references
  -> client polls the server-owned Turn resource
  -> optional Studio resolver links
```

Request admission and terminal reconciliation remain application-service
responsibilities because they decide whether an execution exists and observe
the outer Workflow result or failure. Mandatory AI processing remains explicit
Workflow Nodes. Conditional capabilities remain Agent Tools.

Known specialized behavior remains explicit Workflow structure. The Agent is
not a universal replacement for deterministic product behavior.

## Work packages

### 1. Turn domain and persistence

- Add a schema-versioned immutable Turn object and explicit lifecycle status.
- Allocate the Turn ID and conversation sequence on the server.
- Persist accepted input atomically before Workflow execution.
- Enforce one active Turn per conversation at the backend boundary.
- Store canonical Turn JSON in both SQLite and deterministic in-memory adapters.
- Use exact lifecycle transitions for success, failure, and cancellation.
- Persist Workflow and Agent runtime IDs as execution references.
- Derive messages and conversation history from Turn objects.
- Bound recent context by an explicit versioned context policy.

Client-generated Turn IDs and implicit pairs of message rows are removed from
the application contract. Idempotency-key support is deferred until the
authoritative Turn lifecycle is proven; any later key remains untrusted retry
input rather than domain identity.

### 2. Workflow responsibility split

- Replace input persistence inside the Workflow with application admission.
- Add a dedicated recent-context Node.
- Make `CreateGeneralAgentResponseNode` perform only detached
  state-to-Agent mapping.
- Keep rich history search, contact lookup, and image creation as conditional
  Tools.
- Keep outcome persistence in its own Node.
- Preserve the existing graph, state, factory, service, domain, and adapter
  file boundaries.

### 3. API and browser model

- Replace the message-only read model with Turn-oriented responses.
- Return durable Turn status, messages, and execution references after reload.
- Replace the ephemeral `evidenceByTurnId` map with persisted execution
  references carried by each Turn.
- Use typed RFC 9457-style application problems with the Turn identity and any
  known execution references.
- Add public runtime configuration for debug visibility and the Studio UI
  origin; never send a Studio API key to the browser.

### 4. Junjo execution correlation

- Add the public immutable `ExecutionCorrelation` input.
- Propagate one active value through nested Workflows and Agents.
- Reject conflicting nested correlation.
- Emit the optional all-or-none correlation pair on executable owner spans.
- Update the normalized telemetry schema, fixtures, SDK producer tests, Studio
  consumer tests, and public documentation together.

### 5. Studio execution resolution

- Add an authenticated backend resolver with exact service scope, executable
  type, and runtime ID input.
- Select only executable owner spans and reject ambiguous evidence.
- Return the exact physical identity and Studio-relative destination.
- Add an authenticated frontend resolver route with bounded polling for OTLP
  ingestion delay.
- Redirect resolved Agent and Workflow identities into their existing semantic
  detail views.

### 6. Debug UX and end-to-end proof

- Add an opt-in per-Turn diagnostics panel to AI Chat.
- Link Workflow, Agent, and full-trace diagnostics through Studio's resolver
  URL contract.
- Prove that references survive application reload.
- Prove correlated Workflow, Agent, and nested Workflow owner spans.
- Prove the browser can follow an AI Chat Turn to exact Studio evidence.

## Validation

The change is complete only when:

- AI Chat backend domain, adapter, Workflow, API, failure, concurrency, and
  telemetry tests pass;
- AI Chat frontend schema, hook, component, lint, and production-build tests
  pass;
- Python SDK Ruff, pytest, ty, Sphinx, package build, and Twine validation pass;
- telemetry fixtures regenerate idempotently and contract validation passes;
- Studio backend tests, REST contract generation, frontend tests, lint, and
  production build pass; and
- the AI Chat-to-Studio E2E path resolves exact Workflow and Agent evidence.

## Infrastructure validation record

Validated on 2026-07-14 for the Turn, correlation, resolution, and diagnostic
infrastructure. This does not establish faithful AI Chat product restoration.

- The SDK passed Ruff, ty, 320 deterministic tests, warning-strict Sphinx,
  package build, and Twine validation.
- AI Chat passed 39 backend tests and 18 frontend tests, plus backend type and
  lint checks and frontend lint and production build.
- Telemetry contract generation was idempotent and validation covered 9
  schemas, 6 Workflow producer fixtures, 33 Agent producer fixtures, 4 Agent
  consumer fixtures, 41 invalid fixtures, 22 fingerprint vectors, 7 RFC 6902
  vectors, and 575 bounded malformed-scalar mutations.
- Studio's complete routed suite passed backend, ingestion, frontend, OpenAPI,
  and protobuf validation. The new resolver also has exact-query repository,
  service, router, browser-polling, and generated-contract tests.
- A disposable current-code Studio stack admitted a real Turn asynchronously,
  reloaded its canonical JSON from a fresh application instance, ingested the
  exact fourteen-span reduced demonstration execution tree, verified Turn correlation on
  every executable owner, served one cohesive `TraceEvidence` document,
  resolved the outer Workflow, Agent, and nested Workflow by runtime identity,
  replayed all three Stores, and navigated through the stable resolver URL into
  the Agent and nested Workflow diagnostics UI.

## Explicitly deferred

- client idempotency-key support;
- whole-Turn automatic retries or a Turn-attempt aggregate;
- multi-agent chat;
- incremental public streaming;
- a permanent cloud object-store vendor;
- the generalized schema registry and projection rebuild service owned by
  Horizon 5.
