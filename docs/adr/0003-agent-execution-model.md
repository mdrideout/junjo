# ADR 0003: Agent execution model

- Status: Accepted
- Date: 2026-07-13
- Owners: Junjo platform

## Context

Junjo Workflows are reusable definitions for deterministic graph traversal.
Their Graphs declare possible paths before execution, while models perform
bounded work inside Nodes. The Agent layer supports the complementary case: a
model chooses the next capability at runtime from an explicit set of Tools.

Dynamic selection must not weaken Junjo's established properties:

- reusable definitions and isolated executions;
- typed input, state, and output;
- explicit side effects;
- detached results;
- cancellation distinct from failure;
- lifecycle observation independent from telemetry;
- complete OpenTelemetry diagnostics;
- deterministic testing without a live model.

Representing an Agent as a Node, dynamically generated Workflow, provider-owned
session, or universal executable base would blur existing ownership. A Node
runs inside a Graph, a Workflow declares a Graph, a provider session hides
state, and a universal base would generalize behavior before Agent and Workflow
have demonstrated stable common mechanics.

This ADR owns the Agent definition, run, state, result, limits, terminal
behavior, and non-ownership boundaries. ADR 0004 owns ModelDriver and Tool
contracts. ADR 0005 owns Workflow composition and lifecycle structure. ADR
0006 owns shared telemetry semantics.

## Decision

### Agent is a first-class executable

`Agent` is a reusable Junjo executable definition and a sibling to `Workflow`.
It does not subclass or wrap `Workflow`, `Subflow`, or `Node`, and it does not
fabricate a Graph. Model and Tool operations form a realized execution trace,
not a static execution Graph.

The public definition owns immutable execution structure:

- an application-owned Agent key;
- a human-readable display name;
- instructions;
- the declared input type;
- an immutable ModelDriver binding declaration;
- an ordered collection of Tools;
- the declared final output type;
- positive execution limits.

The definition may also reference a mutable `Hooks` registry. Callback
membership is observer configuration, not structural Agent material, and is
snapshotted per admitted run under ADR 0005. Shared collaborator internals are
also outside structural material; their immutable binding descriptors are
inside it.

Construction is explicit. The core API requires no decorators, docstring
parsing, global registry, provider-owned session, or hidden dependency
injection.

The Agent key is the stable logical identity selected by the application. It
must remain stable across process restarts and deployments when the Agent still
represents the same application capability. The display name may change
without changing that logical identity. An Agent key is unique within the
OpenTelemetry service scope `(service.namespace or "", service.name)`.
That exact service scope plus Agent key is the cross-deployment query identity;
optional `service.version` distinguishes releases when supplied without
splitting the logical Agent.

Four identities remain distinct:

- `key` identifies the logical Agent across deployments;
- `definition_id` identifies one reusable in-process definition object;
- `structural_id` fingerprints behavior-affecting definition material;
- `run_id` identifies one execution.

`run_id` is the public spelling of the common lifecycle `runtime_id`. It is
also emitted as both `junjo.executable_runtime_id` on the Agent span and
`junjo.agent.runtime_id` on the Agent span and its operation spans. These are
the same value, not three identities.

ADR 0006 defines the structural fingerprint material and encoding. A display
name is not a substitute for a stable key, and a generated definition ID is not
a cross-release version.

### Definitions are reusable; runs are isolated

The public execution operation is `Agent.execute()`. Its semantic inputs are:

- typed application input for the current request;
- opaque request-scoped application dependencies;
- optional detached provider-neutral history selected by the application.

Every call first creates an execution identity and diagnostic context, then
validates and detaches its input and history. Boundary validation failure is an
observable typed failure and starts no ModelDriver or Tool work. An admitted
run creates:

- a fresh private Agent state and Store;
- a fresh lifecycle dispatcher with snapshotted observers;
- a fresh telemetry context;
- fresh counters and usage accumulation;
- a fresh run-local collaborator cache for factory-backed bindings;
- no Agent-owned mutable run state shared with another run.

The Agent definition never becomes the live run container. Concurrent calls on
one definition must have independent state, transcripts, counters, results,
telemetry, and factory-created collaborator products. Explicit shared
collaborators may be used concurrently under ADR 0004's caller guarantee.

ADR 0004 requires each shared ModelDriver or Tool service to be explicitly
safe for concurrent use, or to be supplied by a per-run factory. Junjo does not
silently serialize an unsafe collaborator behind a lock.

### Agent state is private, typed, and transition-based

Junjo owns a private Agent run-state model and Store. Application developers do
not define or directly mutate that Store.

Run state contains only information that evolves during one execution:

- validated input and supplied history;
- the ordered normalized model and Tool transcript;
- current model iteration;
- model-request count;
- requested, admitted, started, and completed Tool-call counts;
- normalized provider-reported usage;
- admitted, pending, and completed Tool calls;
- validated final output;
- terminal reason.

State changes occur through explicit private actions. Those actions cover model
responses, Tool-batch admission, Tool results, usage, final output, and terminal
reason. Transitions use Junjo's immutable validated Store pattern and produce
ordered evidence suitable for JSON Patch reconstruction.

Application dependencies are not Agent state. Authentication context,
repositories, database and HTTP clients, storage clients, configuration, and
event sinks remain opaque request-scoped dependencies. The model sees only
values deliberately placed in normalized model input or returned by a Tool.

The implementation may reuse small Store mechanics, but it must not force
graph-shaped lifecycle context onto an Agent or emit fake Graph identities.

### Successful execution returns one detached typed result

`Agent.execute()` returns a frozen `AgentExecutionResult[OutputT]` only after
the final output passes declared validation.

The result contains detached values:

- Agent key, display name, definition ID, and structural ID;
- run ID;
- validated typed output;
- normalized final transcript snapshot;
- normalized usage summary;
- model-request count and requested, admitted, started, and completed Tool-call
  counts;
- terminal reason.

The only successful terminal reason is `final_output`. Success never has a
missing or invalid output. A result exposes no live Store, dependency, driver,
Tool, span, task, or mutable transcript reference.

Applications decide what input, transcript, output, and usage evidence to
persist. Agent execution does not create persistent conversation memory.

### Execution is always bounded

Every Agent has positive effective limits for:

- model requests;
- total Tool calls.

Junjo may provide conservative defaults, but there is no unlimited sentinel.
Budget admission happens before the affected operation begins. When one model
response contains more Tool calls than the remaining budget, the entire batch
is rejected before any Tool in that batch runs.

The Tool-call limit applies to admitted calls. Requested calls can exceed the
limit only in the rejected over-budget batch; no call in that batch is
admitted or started.

Provider token and cost values are accounting facts only in the initial
kernel. Token, cost, and wall-clock enforcement remain deferred. Applications
may impose an outer deadline through normal task cancellation.

### Failure is not partial success

Input or history validation, limit exhaustion, ModelDriver failure, malformed
normalized response, unknown or invalid Tool calls, Tool failure, Tool result
validation, and final-output validation are failures. They never return an
output-less successful result.

Agent failures use a typed hierarchy rooted at `AgentError`. Input and history
rejection are `AgentInvocationError` values because no run-local Store or
public lifecycle has started. Failures after admission are
`AgentExecutionError` values.

Limit exhaustion is specifically `AgentLimitExceededError`. It identifies the
model-request or Tool-call budget, the positive effective limit, and the
attempted next count or requested batch that could not be admitted.

Every Agent error contains the Agent key, definition ID, run ID, terminal
reason, structural ID, and detached diagnostic evidence available at its
boundary. Execution errors include a detached Store snapshot.
Boundary-specific errors preserve the original exception as their cause when
one exists.

ADR 0004 defines the boundary-specific error types. The initial kernel performs
no automatic final-output repair. A candidate is validated once; invalid output
raises an output-validation failure. Any later correction or retry policy
requires a separate bounded decision.

Completed side effects are not rolled back when a later operation fails.
Applications own transactions, compensation, and recoverable domain-result
types.

An invocation failure records the failed Agent span and raises without
dispatching started or failed public hooks. No executable run was admitted.

An admitted execution failure closes or drains Agent-owned work, records the
failed state and span, dispatches exactly one failed lifecycle event, and
raises. No Agent-owned background task may survive a terminal outcome.

### Cancellation is distinct from failure

Cancellation propagates through the active model request, Tool, or nested
Workflow. The runtime:

- begins no new operation after cancellation is observed;
- drains or closes Agent-owned work;
- records cancellation and terminal state;
- dispatches exactly one cancelled lifecycle event;
- re-raises `asyncio.CancelledError`.

Cancellation is not wrapped as an Agent failure, returned as partial success,
or marked as an OpenTelemetry error solely because it was cancelled.

### Lifecycle and telemetry ship with execution

After input and history admission, the initial public Agent lifecycle is
limited to started, completed, failed, and cancelled events. Hooks are optional
observers and cannot become execution or telemetry control flow. Hook failures
do not change an Agent outcome.

Model and Tool operations require semantic telemetry but no public hooks in the
initial kernel. ADR 0005 defines lifecycle identity and observer snapshotting.
ADR 0006 defines spans, state events, payload policy, ordering, and conformance.

The initial public Agent API is non-streaming. A ModelDriver returns one fully
assembled normalized response. A provider adapter may assemble a provider
stream internally, but partial chunks do not mutate Agent state or define a
public transport.

Agent behavior and its semantic telemetry are one implementation unit. A
runtime behavior is incomplete until deterministic tests prove its state
transitions, terminal behavior, and observable hierarchy.

### Persistence and product policy remain application-owned

Agent does not own:

- chat-session or long-term-memory persistence;
- authentication or authorization policy;
- HTTP, WebSocket, command-line, or product-event transport;
- database transaction lifetime;
- provider credentials as global state;
- durable background jobs;
- evaluation datasets or promotion policy;
- source-code modification;
- Junjo AI Studio storage or query mechanics.

The application selects history and dependencies before execution and persists
selected detached results afterward.

## Implementation requirements

Horizon 1 must prove this decision with deterministic SDK tests for:

- direct typed completion;
- input and history rejection before model or Tool work;
- limit exhaustion before an over-budget operation;
- ModelDriver, Tool, malformed-response, and output-validation failures;
- cancellation during model, Tool, and nested Workflow execution;
- detached successful and failed diagnostic snapshots;
- repeated and concurrent execution of one Agent definition;
- shared-safe and per-run collaborator construction;
- lifecycle-observer snapshot isolation;
- absence of shared Agent-owned mutable run state;
- complete state reconstruction from ordered transitions;
- exactly one terminal outcome and no surviving Agent-owned work.

The kernel lives in `sdks/python/src/junjo`. The `ai_chat` example consumes the
public API and may not hide runtime mechanics that belong in the SDK.

## Consequences

Positive consequences:

- Agent and Workflow have equally explicit but truthful execution models;
- dynamic behavior does not contaminate Graph contracts;
- typed completion remains strong because failure is never partial success;
- applications retain persistence, dependency, transport, and transaction
  ownership;
- one Agent definition can serve concurrent requests safely;
- stable logical and structural identities support cross-release diagnosis.

Costs and constraints:

- the SDK needs a dedicated private loop, state model, result, and error
  hierarchy;
- common lifecycle identity must be separated from Graph-only identity;
- structural comparison requires canonical definition material;
- applications must map history, dependencies, composition, and persistence;
- provider adapters cannot dictate Junjo execution semantics.

## Rejected alternatives

- Agent as a Node: a standalone Agent has no owning Graph or Workflow Store.
- Agent as a dynamic Workflow: no honest static execution Graph exists before
  the model realizes operations.
- Agent as a Workflow subclass: graph traversal and Store contracts do not
  describe Agent execution.
- Provider-owned conversation sessions: they hide state and weaken
  deterministic replay.
- Mutable state on the Agent definition: concurrent runs would leak state.
- Optional-output success results: they permit accidental treatment of failure
  as success.
- Unlimited execution: an autonomous loop requires deterministic bounds.
- Universal executable base class now: commonality should be extracted only
  after concrete duplication is proven.
- Telemetry added after the kernel: observable behavior is part of the runtime
  contract.

## Related decisions

- [ADR 0004: Agent ModelDriver and Tool contracts](0004-agent-model-driver-and-tool-contracts.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
