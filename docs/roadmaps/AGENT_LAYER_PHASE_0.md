# Agent Layer Phase 0: Architecture And Telemetry Decisions

## Status

Complete as of 2026-07-13.

Root ADRs 0003 through 0006 and Studio ADRs 004 and 007 are accepted and
normative. This document remains the Horizon 0 traceability and
implementation-sequencing record. All Horizon 0 exit criteria are satisfied,
and its Horizon 1 and Horizon 2 implementation outcomes are linked below.

Horizon 0 produced architectural decisions only. At its completion it did not
claim an implemented Agent runtime, telemetry contract version 2, or Studio
Agent view. The current implementation status lives in
[AGENT_LAYER_ROADMAP.md](AGENT_LAYER_ROADMAP.md).

## Objective

Define the smallest coherent Agent runtime that can be built on Junjo's
existing architectural principles without weakening the Workflow, Graph,
State, Store, Execution, Lifecycle, Hook, Telemetry, or Studio boundaries.

The design must support dynamic model-selected capabilities while preserving:

- reusable definitions and isolated runs;
- typed input, state, Tools, and output;
- explicit application-owned side effects;
- bounded execution and detached results;
- failure and cancellation semantics;
- deterministic tests;
- complete shared-contract diagnostics in Studio.

## Accepted decision set

| Decision | Status | Ownership |
| --- | --- | --- |
| [ADR 0003: Agent execution model](../adr/0003-agent-execution-model.md) | Accepted | Agent definition, run, state, result, limits, terminal behavior |
| [ADR 0004: Agent ModelDriver and Tool contracts](../adr/0004-agent-model-driver-and-tool-contracts.md) | Accepted | Typed normalized model and application capability boundaries |
| [ADR 0005: Agent and Workflow composition](../adr/0005-agent-workflow-composition.md) | Accepted | Composition, lifecycle identity, hooks, nested propagation |
| [ADR 0006: Agent telemetry contract](../adr/0006-agent-telemetry-contract.md) | Accepted | Contract v2 spans, operations, state revisions, payloads, fixtures |
| [Studio ADR 004: Span Events JSON Contract](../../apps/studio/docs/adr/004-events-json-contract.md) | Accepted | Canonical stored event shape and dropped-attribute mapping |
| [Studio ADR 007: Agent execution diagnostics](../../apps/studio/docs/adr/007-agent-execution-diagnostics.md) | Accepted | Ingestion preservation, semantic queries, diagnostic UI |

The ADRs are the source of truth. This record summarizes their boundaries
without redefining their detailed contracts.

## Architectural result

`Agent` is a first-class executable sibling to `Workflow`. It owns a private,
bounded model/Tool loop and produces a typed detached result. It is not a Node,
Workflow subclass, dynamic Graph, provider session, or persistence layer.

The initial composition is:

`Application -> Agent definition -> isolated Agent run`

An Agent run collaborates with:

- a ModelDriver that translates one normalized request into one normalized
  response;
- explicit typed Tools that call application services;
- ordinary application Nodes and Tool services for Workflow composition;
- lifecycle observers that cannot control execution or telemetry;
- OpenTelemetry emission consumed through the shared platform contract.

### Responsibility map

| Layer | Owns | Does not own |
| --- | --- | --- |
| Agent definition | Stable key, display configuration, declared schemas, collaborator bindings, limits | Live run state, persistence |
| Private Agent execution | Validation, loop, Store transitions, limits, terminal behavior | Provider translation, application side effects |
| ModelDriver binding | Declared model identity and collaborator ownership | Provider calls or Agent looping |
| ModelDriver | Provider request/response translation and usage extraction | Declared identity, looping, Tools, lifecycle, Junjo telemetry policy |
| Tool | Typed capability definition and application service boundary | Private Agent Store or transcript mutation |
| Application | Dependencies, authorization, persistence, transactions, transport, recovery policy | Junjo runtime mechanics |
| Lifecycle | Run-local public observer dispatch | Telemetry control or product transport |
| Shared telemetry contract | Semantic evidence, ordering, fixtures, producer/consumer conformance | Runtime control or Studio storage |
| Studio ingestion | Preservation of shared-contract OTLP evidence | Agent interpretation |
| Studio backend | Typed Agent queries and semantic assembly | SDK internals or frontend presentation |
| Studio frontend | Dynamic timeline, state exploration, nested Workflow navigation | Physical telemetry queries or contract inference |

The governing rule is:

> The Agent decides, Junjo executes, Tools perform application work, telemetry
> explains, and Studio interprets.

## Resolved Horizon 0 questions

### Identity and isolation

- Applications declare a stable Agent key.
- Definition, structural, and run identity remain separate.
- Agent structural configuration and collaborator bindings are immutable and
  reusable; referenced hook membership is mutable but snapshotted per run.
- Every admitted execution owns fresh state and run-local machinery.
- Shared collaborators require an explicit concurrency-safety guarantee;
  otherwise applications supply per-run factories.
- Hook callback membership is snapshotted when an executable starts.

### Typed model and Tool boundaries

- Agent and Tool inputs and outputs are Pydantic `TypeAdapter`-compatible,
  schema-capable, and JSON-serializable.
- History and transcript use a closed provider-neutral message model.
- A ModelDriver returns exactly one final-output response or one non-empty
  ordered Tool-call response.
- ModelDriver and Tool boundaries never expose provider SDK objects or private
  Agent state.
- Tool batches are budgeted, resolved, and validated before any service runs.
- Initial Tool execution is sequential and preserves model-returned order.
- Final output is validated once; there is no automatic correction retry.
- Core initially provides contracts and deterministic scripted support, not an
  official provider dependency.

### Workflow composition and lifecycle

- Workflow-to-Agent mapping lives in an ordinary application Node.
- Agent-to-Workflow mapping lives in an ordinary application Tool service.
- Parent and child Stores, limits, identities, hooks, and results remain
  independent.
- Failures and cancellation propagate through every owning boundary unless
  application code explicitly handles a domain outcome.
- Common executable identity and Graph-only identity are separate.
- Public Agent hooks are limited to started, completed, failed, and cancelled.
- No generic AgentNode, WorkflowTool, or universal executable base is introduced
  before repetition proves one necessary.

### Telemetry and Studio

- Agent semantics and generic Store revisions form telemetry contract version
  2.
- The Agent is an executable span; model and Tool spans are ordered Agent
  operations, not fake Graph executables.
- Structural identity is computed from canonical pre-policy definition material.
- Full normalized requests, responses, Tool values, and state evidence are the
  default proof contract.
- Payload transformation is explicit; nothing is silently truncated.
- Store transitions use monotonic sequence and revision numbers plus RFC 6902
  patch arrays.
- Store-owning spans publish expected transition counts and terminal revisions
  so missing evidence is detectable.
- Studio renders a realized Agent timeline/tree and preserves nested Workflow
  Graph views.
- Ingestion preserves contract evidence and OTLP loss signals, the backend owns
  semantic queries and reconstruction integrity, and the frontend owns
  presentation and verified state navigation.

## Contract rollout boundary

Horizon 0 required telemetry contract version 1 to remain active until the
complete producer and consumer implementation existed. Horizon 1 fulfilled
that requirement as one atomic version 2 platform change containing:

1. telemetry contract version 2 and schemas;
2. updated Workflow fixtures, payload slots, and Store producer behavior;
3. canonical Agent producer, consumer, invalid, and fingerprint fixtures;
4. SDK Agent runtime and telemetry producer conformance;
5. public Agent docstrings, owned Markdown teaching surfaces, and testing guidance;
6. Studio resource and loss-signal preservation;
7. Studio backend semantic Agent queries and Store integrity;
8. Studio frontend Agent diagnostics;
9. cross-component validation.

These pieces were developed incrementally on one branch and must merge as one
compatible source state rather than as producer-only or consumer-only changes.
Their independently versioned artifacts then follow one coordinated greenfield
cutover: publish Python SDK `0.65.0` first, accept a temporary
semantic-diagnostics outage, and publish Studio `0.82.0` or newer with its
canonical deployment pins and generated mirrors bound to that installable SDK.
Version 1 is rejected after the Studio cutover; no fallback is added. Version
and deployment-pin changes happen during release preparation, not on this
implementation branch.

## Post-Horizon-0 implementation sequence

### Work package 1: architectural decisions

Complete. ADRs 0003 through 0006 and Studio ADRs 004 and 007 are accepted.

### Work package 2: lifecycle preparation

Complete in Horizon 1.

Separate common executable identity from Graph-only identity, snapshot Hooks per
run, and preserve existing Workflow behavior except for the accepted
callback-membership snapshot change before adding Agent behavior.

### Work package 3: deterministic Agent kernel

Complete in Horizon 1.

Implement public typed definitions and contracts plus the private isolated
model/Tool loop, Store, limits, result, failures, cancellation, and scripted
ModelDriver support.

### Work package 4: telemetry contract version 2

Complete in Horizon 1.

Implement Store revisions and owner counts, Agent and operation spans, the
built-in full payload policy, canonical valid and invalid fixtures, structural
fingerprint conformance, and SDK producer tests with the kernel.

### Work package 5: Studio consumer support

Complete in Horizon 1.

Implement ingestion preservation tests, typed backend Agent queries and shared
Store integrity, frontend schemas and dynamic execution diagnostics, and
canonical consumer conformance.

### Work package 6: public Agent teaching surfaces

Complete in Horizon 1.

Ship complete public API docstrings, owned Markdown concepts, generated API documentation,
deterministic scripted-testing guidance, composition examples, and telemetry
conformance guidance with the Horizon 1 runtime. These surfaces must state that
an Agent is a first-class executable and never describe it as a generated
Graph.

Work package 2 may merge independently after existing Workflow behavior remains
green because it does not activate Agent telemetry. Work packages 3 through 6
comprise the compatible Agent runtime, evidence path, and public contract; they
cross the merge boundary together.

### Work package 7: AI Chat proof

Complete in Horizon 2.

Use the public Agent API in `sdks/python/examples/ai_chat` with explicit live
Gemini and Grok adapters, application-owned integration checks, a conversation
query Tool, and a structured Workflow Tool. Scripted drivers remain SDK-test
infrastructure and are never treated as AI Chat product behavior. This is
complete in Horizon 2.

The canonical acceptance cases are the nine
[Initial AI Chat Acceptance Scenarios](AGENT_LAYER_ROADMAP.md#initial-ai-chat-acceptance-scenarios)
in the strategy roadmap.

### Work package 8: live evaluations

Horizon 2 adds application-owned opt-in datasets and commands after the
deterministic kernel is stable. Live credentials and probabilistic evals remain
outside default CI. Horizon 3 builds Studio measurement and comparison on top
of this proven application eval loop.

## Horizon 1 validation gates

### Python SDK

- Ruff;
- deterministic pytest suite;
- ty;
- complete public Agent docstrings, owned concepts/generated API pages, deterministic
  testing guidance, and telemetry conformance guidance;
- Griffe public-surface and unified documentation failures treated as release errors;
- package build and Twine validation;
- repeated and concurrent Agent isolation;
- complete terminal and cancellation coverage.

### Shared telemetry contract

- dependency-free contract validator;
- Workflow and Agent fixture schema validation;
- RFC 8785 fingerprint conformance;
- Store reconstruction from counts, revisions, and patches;
- corrupt-derivative rejection and loss-signal preservation;
- SDK producer equivalence for the producer fixture set.

### Studio

- ingestion contract preservation;
- backend semantic summary and detail queries;
- frontend schemas and Agent diagnostics;
- authoritative backend Workflow/Agent Store reconstruction and frontend
  navigation over verified projections;
- nested Workflow Graph matching;
- `apps/studio/run-all-tests.sh`.

## Horizon 2 validation gates

### AI Chat

- deterministic application integration tests with no provider credentials;
- public Junjo APIs only;
- no timing sleeps or untracked background execution on the canonical path.
- all nine canonical acceptance scenarios pass.

## Explicitly deferred

Horizon 0 does not design:

- multi-agent managers or handoffs;
- persistent sessions or long-term memory;
- MCP;
- parallel Tools;
- public incremental streaming;
- automatic output repair;
- retries, provider fallback, or token/cost enforcement;
- durable background execution;
- generated Workflows, schemas, or interfaces;
- source-code modification;
- evaluation promotion policy;
- Agent-queryable Studio APIs;
- a universal executable abstraction.

Each requires evidence from the preceding horizons and a focused decision when
it becomes current.

## Exit criteria

- [x] Root Agent ADRs 0003 through 0006 are accepted.
- [x] Studio span-event transport ADR 004 is revised for contract version 2.
- [x] Studio Agent diagnostics ADR 007 is accepted.
- [x] Agent ownership and non-ownership boundaries are explicit.
- [x] State, dependency, ModelDriver, Tool, result, and terminal contracts are
  defined.
- [x] Workflow/Agent composition is explicit without premature adapters.
- [x] Lifecycle refactoring scope and hook snapshot behavior are defined.
- [x] Telemetry identities, operations, attributes, events, ordering, and
  hierarchy are defined.
- [x] Structural fingerprint and payload policy boundaries are defined.
- [x] Deterministic contract fixtures and producer/consumer obligations are
  specified.
- [x] Studio query, state reconstruction, and UI expectations are specified.
- [x] Canonical AI Chat acceptance scenarios and validation layers are agreed.

Horizon 0 is complete. Horizon 1 and Horizon 2 implementation outcomes are
recorded in the strategy roadmap.
