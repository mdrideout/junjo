# ADR 0003: Agent execution model

- Status: Proposed
- Date: 2026-07-13
- Owners: Junjo platform

## Context

Junjo Workflows are reusable definitions for deterministic graph traversal.
Their graphs define the possible paths before execution, while models perform
bounded work inside Nodes. The Agent layer must support the complementary case:
a model chooses the next capability at runtime from an explicit set of Tools.

That dynamic choice must not weaken the properties already established by the
Workflow runtime:

- reusable definitions and isolated executions;
- typed state and outputs;
- explicit side effects;
- detached results;
- cancellation distinct from failure;
- lifecycle observation independent from telemetry;
- complete OpenTelemetry diagnostics;
- deterministic testing without a live model.

An Agent could be represented as a Node, a dynamically generated Workflow, a
provider-owned conversation, or a generic executable abstraction. Each option
would blur an existing ownership boundary. A Node runs inside a Graph, a
Workflow declares a Graph, a provider conversation delegates state ownership to
an external SDK, and a universal executable base would generalize before Agent
and Workflow behavior have demonstrated stable common mechanics.

This ADR decides the Agent definition, execution, state, result, limits,
failure, cancellation, and identity model. ADR 0004 owns normalized model and
Tool contracts. ADR 0005 owns Workflow composition and lifecycle structure.
ADR 0006 owns the shared telemetry schema and producer/consumer conformance.

## Decision

### Agent is a first-class executable

`Agent` is a reusable, first-class Junjo executable definition and a sibling to
`Workflow`.

It does not subclass or wrap `Workflow`, `Subflow`, or `Node`. It does not
fabricate a Graph or Graph structural identities. The realized model and Tool
operations form a dynamic execution trace, not a static execution Graph.

The public Agent definition owns configuration:

- a generated definition ID that remains stable for that definition object;
- a human-readable name;
- instructions;
- the declared input type;
- an injected model driver;
- an ordered collection of explicit Tools;
- the expected final output type;
- explicit execution limits;
- optional Agent lifecycle observers.

Construction is explicit. The core API does not require decorators, docstring
parsing, global registration, provider-owned sessions, or hidden dependency
injection. Structural configuration is normalized and immutable after
construction so one definition can be reused safely.

Injected collaborators need an explicit concurrency contract. ADR 0004 must
require each model driver and Tool service either to be safe for concurrent
calls or to be supplied through a per-run factory. ADR 0005 must define how the
existing mutable Hooks registry is snapshotted at execution start so observer
registration cannot change an active run. These collaborator rules are part of
the Horizon 1 isolation tests.

### Every execution is isolated

The public execution operation is `Agent.execute()`.

Its semantic shape is:

```python
result = await agent.execute(
    input=agent_input,
    dependencies=run_dependencies,
    history=prior_history,
)
```

`input` is typed application data for this request. It is validated and copied
into detached run state before the first model call. `dependencies` contains
request-scoped services available to Tools. `history` is an optional detached,
provider-neutral transcript supplied by the application. ADR 0004 defines the
exact `InputT`, validation, normalized message, driver, dependency-context, and
Tool types.

Every call creates:

- a fresh runtime ID;
- a fresh private Agent state and Store;
- a fresh lifecycle dispatcher;
- a fresh telemetry context;
- fresh counters and usage accumulation;
- no Agent-owned mutable run state shared with any other run.

The Agent definition never becomes the live run container. Executing the same
definition concurrently must be safe and must produce independent state,
transcripts, counters, results, and telemetry.

### Agent state is private, typed, and transition-based

Junjo owns a private Agent run-state model and Store. Application developers do
not define an Agent Store for ordinary use and cannot mutate the internal Store
directly.

The state contains only information that evolves during one execution:

- normalized input and supplied history;
- the ordered model and Tool transcript;
- current model iteration;
- model-request and Tool-call counts;
- accumulated usage reported by the model driver;
- pending Tool calls;
- completed Tool results;
- validated final output;
- terminal reason.

State changes occur through explicit actions. The initial implementation needs
actions equivalent to appending a model response, admitting Tool calls,
appending a Tool result, updating usage, setting final output, and setting the
terminal reason.

Transitions use Junjo's immutable, validated Store pattern and emit lifecycle
evidence suitable for JSON Patch reconstruction. The implementation may reuse
small internal Store mechanisms, but it must not make Workflow's graph-shaped
lifecycle context generic by adding fake or meaningless values.

Application dependencies are not Agent state. Authentication context,
repositories, database clients, HTTP clients, storage clients, configuration,
and event sinks remain opaque request-scoped dependencies. The model sees only
values deliberately included in normalized model input or returned by a Tool.

### Successful execution returns a detached typed result

`Agent.execute()` returns a frozen `AgentExecutionResult[OutputT]` only after a
final output has passed the declared output validation.

The result contains detached values:

- runtime ID;
- definition ID;
- Agent name;
- validated typed output;
- normalized final transcript snapshot;
- usage summary;
- model-request count;
- Tool-call count;
- terminal reason.

The successful terminal reason is `final_output`. A successful result never has
a missing or invalid output. It exposes no live Store, driver, Tool, dependency,
span, task, or mutable transcript reference.

Applications decide what input, transcript, output, or usage information to
persist. Agent execution does not create persistent conversation memory.

### Definition and structural identity remain distinct

The definition ID follows the existing Workflow-definition principle: it
identifies one reusable in-process definition object. Each execution has a
separate runtime ID.

Cross-process and cross-release comparison uses a deterministic structural
fingerprint derived from canonical structural definition material. That input
is computed before telemetry payload redaction and excludes arbitrary Python
callable identity. The fingerprint is not overloaded onto the definition ID.
ADR 0004 must require stable declared model-driver and Tool identities; ADR 0006
defines the canonical fingerprint material, emitted diagnostic snapshot,
payload-policy transformation metadata, and telemetry attributes.

### Execution is always bounded

No Agent run is unbounded. The initial `AgentLimits` contract includes positive
limits for:

- model requests;
- total Tool calls.

Junjo may provide conservative defaults, but every execution has effective
limits and records them in its definition snapshot and telemetry. An
application can choose stricter limits for a definition; it cannot select an
unlimited sentinel.

Budget admission happens before starting the affected model or Tool operation.
A model response containing more Tool calls than the remaining budget fails
before any call in that response is executed. This avoids a partially executed
batch whose admission depended on iteration order.

Provider token and cost limits are deferred until ADR 0004 defines which usage
values are reliable across drivers. Wall-clock deadlines remain application
cancellation policy initially; the Agent runtime must respond correctly to
cancellation at every await boundary.

### Failure is not partial success

Limit exhaustion, model failure, Tool failure, malformed normalized output, and
final-output validation failure do not return a successful
`AgentExecutionResult`.

They raise typed Agent execution errors. The base error exposes the definition
ID, runtime ID, terminal reason, and a detached diagnostic snapshot of the
state accumulated before failure. More specific error ownership is divided as
follows:

- this ADR requires a distinct limit-exhaustion error;
- ADR 0004 defines model, Tool, malformed-response, and output-validation error
  contracts;
- ADR 0005 defines nested Workflow propagation.

Junjo does not silently turn arbitrary exceptions into model-visible text.
ADR 0004 decides whether the initial kernel supports a bounded, explicit
output-validation correction policy. Without that accepted policy, validation
failure terminates execution rather than silently asking the model to repair
it.

Failure must close or drain owned work, dispatch the failed lifecycle event,
record failure on the active span, and then raise. No Agent-owned background
task may survive terminal execution.

### Cancellation is distinct from failure

Cancellation propagates through the active model request, Tool, or nested
Workflow. The runtime drains or closes Agent-owned work, records the terminal
state and cancellation evidence, dispatches the cancelled lifecycle event, and
re-raises `asyncio.CancelledError`.

Cancellation is not wrapped as an Agent failure, is not returned as a partial
success, and does not set OpenTelemetry error status. No further model or Tool
operation may begin after cancellation is observed.

### Lifecycle and telemetry ship with execution

The initial public Agent lifecycle consists of started, completed, failed, and
cancelled events. Hooks are optional observers and cannot become execution or
telemetry control flow. Hook failures do not change the Agent outcome; they are
recorded on the real active Agent span using the same policy as existing Junjo
executables.

Model and Tool operations require semantic telemetry but do not require public
hooks in the initial kernel. ADR 0005 decides the exact common versus
graph-specific lifecycle contexts. ADR 0006 decides span attributes, state
events, payload policy, ordering, fixtures, and Studio conformance.

Incremental public streaming is not part of the initial kernel. A driver returns
one fully assembled normalized response to the Agent execution loop. A provider
adapter may assemble a provider stream internally, but partial chunks do not
mutate Agent state, dispatch public lifecycle events, or define a transport API.
Any later incremental Agent streaming surface requires a focused decision that
keeps provider assembly, Agent lifecycle, telemetry, and application transport
separate.

Agent execution code and its semantic telemetry are implemented together. A
runtime behavior is incomplete until deterministic tests prove its state
transitions, terminal behavior, and observable execution hierarchy.

### Persistence and transport remain application-owned

Agent does not own:

- chat-session or long-term-memory persistence;
- user authentication or authorization policy;
- HTTP, WebSocket, command-line, or product-event transport;
- database transaction lifetime;
- provider credentials as global Agent state;
- durable background jobs;
- eval datasets or promotion policy;
- source-code modification;
- Junjo AI Studio storage or query mechanics.

The application selects prior history and dependencies before execution and
persists selected detached results afterward.

## Implementation requirements

Horizon 1 must prove this decision with deterministic SDK tests for:

- direct typed completion;
- limit exhaustion before an over-budget operation;
- model, Tool, malformed-response, and output-validation failures;
- cancellation during model and Tool execution;
- detached result and failure snapshots;
- repeated and concurrent execution of one Agent definition;
- shared-collaborator rejection or per-run construction according to the
  accepted ADR 0004 contract;
- lifecycle-observer snapshot isolation according to ADR 0005;
- absence of shared mutable run state;
- complete state reconstruction from ordered transitions;
- no surviving Agent-owned work after any terminal outcome.

The kernel must live in `sdks/python/src/junjo`. The `ai_chat` example consumes
the public API and may not hide runtime mechanics that belong in the SDK.

## Consequences

Positive consequences:

- Agent and Workflow have equally explicit but truthful execution models;
- dynamic behavior does not contaminate Graph contracts;
- typed output remains strong because failure and limit exhaustion are not
  represented as output-less successful results;
- applications keep control of persistence, dependencies, and transport;
- one definition can serve concurrent requests safely;
- telemetry and Studio can reconstruct realized behavior from run-local state
  and operations.

Costs and constraints:

- the SDK needs a dedicated private execution loop, state model, result, and
  typed error hierarchy;
- genuinely common lifecycle identity must be separated from Graph identity
  carefully rather than made nullable everywhere;
- structural comparison requires a canonical Agent definition snapshot;
- applications must explicitly map history, dependencies, and persistence;
- provider adapters cannot dictate Junjo execution semantics.

## Rejected alternatives

- Agent as a Node: rejected because a standalone Agent has no owning Graph or
  Workflow Store and should not receive fabricated Graph identity.
- Agent as a dynamic Workflow: rejected because the model realizes operations
  at runtime and no honest static Graph snapshot exists beforehand.
- Agent as a Workflow subclass: rejected because it would inherit graph
  traversal and Store contracts that do not describe Agent execution.
- Provider-owned conversation sessions: rejected because they hide state,
  couple execution to one provider, and weaken deterministic replay.
- Mutable state on the Agent definition: rejected because concurrent runs would
  share transcripts, counters, usage, or terminal state.
- One result type with optional output for success and failure: rejected because
  it weakens typed completion and permits accidental treatment of failure as
  success.
- Unlimited execution: rejected because an autonomous loop must have a
  deterministic terminal bound.
- Universal executable base class now: rejected because Workflow and Agent
  commonality should be extracted only after concrete duplication is proven.
- Telemetry added after the kernel: rejected because observable state and
  terminal semantics are part of the execution contract, not optional
  instrumentation.
