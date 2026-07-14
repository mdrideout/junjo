# ADR 0005: Agent and Workflow composition

- Status: Accepted
- Date: 2026-07-13
- Owners: Junjo platform

## Context

Agents and Workflows solve different execution problems but must compose in
both directions. Composition must preserve each runtime's truthful identity,
state, limits, result, lifecycle, and telemetry. A generic adapter introduced
before the mappings are understood would either hide application policy or
force Agent behavior into Graph contracts.

The existing lifecycle layer is graph-shaped. Its common event base requires
Graph structural fields, its Store context combines telemetry and hook
dispatch, and its dispatcher observes a mutable Hooks registry throughout a
run. A standalone Agent cannot reuse those contracts honestly.

This ADR owns Agent/Workflow composition, executable lifecycle identity, public
Agent hooks, observer snapshotting, and nested terminal propagation. It does
not own model and Tool data types or emitted telemetry names.

## Decision

### Composition uses ordinary application boundaries first

The initial implementation has no generic `AgentNode`, `WorkflowTool`, direct
Agent Graph member, automatic Store mapper, or universal executable adapter.

Applications compose the runtimes through the boundaries they already own:

- a Workflow Node may execute an Agent;
- a Tool service may execute a Workflow.

The mapping code remains visible application code until repeated use proves a
small adapter would remove brittle duplication without hiding policy.

### Workflow executes Agent through an application Node

An application Node owns this sequence:

1. read a detached snapshot from its Workflow Store;
2. map selected state into typed Agent input and history;
3. assemble request-scoped Agent dependencies;
4. await `Agent.execute()`;
5. map the detached `AgentExecutionResult` into explicit Store actions.

No live Workflow Store is passed to the Agent or its Tools. Agent state is
independent from Workflow state. The Node owns every input and output mapping,
including whether any transcript or usage evidence becomes Workflow state.

The Agent span is a child of the active Node span. The Node is the semantic
parent executable for lifecycle identity. The Agent receives no fabricated
Graph identity.

An uncaught Agent execution error fails the Node and therefore the Workflow.
The original Agent error remains the cause and retains its own diagnostic
evidence. An application may catch a specific Agent error and commit an
explicit recovery state, but that is application behavior rather than an
implicit Junjo fallback.

### Agent executes Workflow through an application Tool

A Tool service owns this sequence:

1. pass validated Tool input and dependencies to an application-owned
   Workflow factory;
2. receive a fresh Workflow definition whose zero-argument Store and Graph
   factories safely close over detached per-call values;
3. await the Workflow through its normal public execution API;
4. map the detached `ExecutionResult` into the declared Tool output.

An existing reusable Workflow definition may be used only when it needs no
per-call data in its Store or Graph factories. The Agent layer does not add
input or dependency parameters to `Workflow.execute()` and does not mutate
factory closures on a shared definition.

The Workflow keeps its own definition ID, run ID, Graph structural identity,
Store, hooks, limits, and result. It is a normal Workflow, not a Subflow and not
an Agent Store adapter.

The nested Workflow span is a child of the active Tool operation span. Because
a Tool is an operation rather than an executable, the Agent is the semantic
parent executable recorded in lifecycle identity. The Workflow keeps and emits
its normal Graph snapshot; that Graph is never copied into Agent state or Tool
attributes.

An uncaught Workflow exception fails the Tool service and becomes an
`AgentToolError` with the Workflow exception preserved as its cause. A Tool may
translate a known Workflow domain failure into a typed recoverable Tool result,
but only through explicit application code.

### State and limits remain independent

Composition never shares a live Store across executable boundaries. Parent and
child each own:

- definition and run identity;
- private execution state;
- limits and counters;
- lifecycle observers;
- detached result;
- terminal outcome.

Workflow iteration limits and Agent model-request and Tool-call limits are
independent. There is no implicit global budget, deadline, transaction, or
rollback.

Completed child work and side effects remain real when a later parent operation
fails. Applications own transaction scope, compensation, and idempotency.

### Common lifecycle identity is separated from Graph identity

The lifecycle domain uses immutable value objects or tagged contexts, not a
universal runtime superclass.

Common executable identity contains:

- definition ID;
- runtime ID;
- name;
- executable type;
- deterministic structural ID;
- a non-recursive parent executable reference when nested.

For an Agent, common `runtime_id` is exactly the public Agent `run_id`. ADR
0006 maps that one value to the generic Agent-span runtime attribute and the
Agent owner-runtime attribute used by child operation spans.

The parent reference contains the parent's definition ID, runtime ID,
structural ID, and executable type. It does not recursively contain its own
parent.

Graph-specific identity extends that semantic data with:

- enclosing Graph structural ID;
- the distinct parent Graph structural relationship when applicable;
- compiled Node structural identities required by the Graph runtime.

Agent-specific identity extends common data with:

- stable Agent key;
- Agent Store ID.

Agent fingerprints are valid executable structural IDs, but they are never
used as enclosing Graph IDs. Graph fields are neither fabricated nor made
nullable on a universal event merely to accommodate Agent.

Lifecycle executable type is a domain concept independent from the telemetry
schema. ADR 0006 maps executable and operation concepts into OpenTelemetry
attributes.

### Public event bases preserve truthful fields

Public hooks use:

- a common event base for common executable and trace identity;
- a Graph event base for Workflow, Subflow, Node, RunConcurrent, and Workflow
  Store fields;
- Agent event types for Agent key, structural identity, Store, result, failure,
  and cancellation evidence.

The initial Agent hook surface is limited to:

- `on_agent_started`;
- `on_agent_completed`;
- `on_agent_failed`;
- `on_agent_cancelled`.

Started events contain immutable identity and Store metadata. Completed events
contain the detached Agent result. Failed and cancelled events contain detached
diagnostic state when a Store was created, plus their error or cancellation
reason.

There are no public model-request, Tool-call, or Agent-state-transition hooks
in the initial kernel. Those are diagnostic operations owned by telemetry.
Existing Workflow state-change hooks remain Graph lifecycle events and are not
silently extended to private Agent state.

### Hook membership is snapshotted per run

After boundary input and history validation, each admitted executable copies
the relevant callback membership from the supplied `Hooks` registry into the
run-local dispatcher and dispatches its started event. Rejected Agent
invocations are telemetry-visible but do not dispatch public lifecycle hooks.

Registration or unsubscription after that snapshot affects future runs only.
It cannot add or remove callbacks from an active run. Workflow Node and Store
events use the owning Workflow run's dispatcher snapshot.

Nested definitions use their own configured hooks. Hooks are not inherited or
merged automatically across Agent/Workflow boundaries. An application may
explicitly pass the same registry to multiple definitions; each run snapshots
it independently.

Snapshotting protects registry membership, not callback internals. An
application-supplied callback must itself be safe if concurrent runs can invoke
it.

Callbacks execute in registration order. An ordinary callback exception is
recorded on the real active executable span, does not alter execution outcome,
and does not stop later callbacks.

Cancellation has an explicit terminal boundary:

- task cancellation during a started or non-terminal callback propagates
  through the executable's normal cancellation path;
- the executable commits exactly one terminal outcome before dispatching its
  terminal event;
- task cancellation delivered during terminal callback dispatch is recorded as
  observer-delivery cancellation, stops remaining callbacks, propagates to the
  caller, and does not rewrite the committed Agent outcome or emit a second
  terminal event;
- a callback that directly raises `asyncio.CancelledError` when the surrounding
  task has no pending cancellation is an observer failure and is isolated like
  another callback exception.

Terminal observers therefore cannot convert a completed or failed Agent span
to cancelled. As with cancellation after an external side effect commits, the
caller may not receive the already committed result or error if its task is
cancelled during terminal notification.

Telemetry never depends on public hook dispatch.

### Failure and cancellation propagate at every owning boundary

Failure is recorded by each boundary that owns the failing operation:

- Agent failure inside a Node fails the Agent, then Node, then Workflow unless
  application code explicitly recovers;
- Workflow failure inside a Tool fails the Workflow, then Tool, then Agent
  unless application code returns a typed recoverable Tool result.

Errors preserve their causes rather than being flattened into text.

Cancellation propagates unchanged through:

- Workflow to Node to Agent;
- Agent to Tool to Workflow.

Every active executable and operation records cancellation, begins no new work,
drains its owned work, and re-raises `asyncio.CancelledError`. Cancellation is
not converted to failure at a composition boundary.

### OpenTelemetry context establishes runtime parentage

Composition relies on the active OpenTelemetry context:

`Workflow -> Node -> Agent -> model/Tool operations`

`Agent -> Tool operation -> Workflow -> Nodes`

Callers do not pass fake Graph identifiers to create this hierarchy. Semantic
parent executable reference remains explicit because a Tool operation can sit
between two executable spans.

## Implementation requirements

Horizon 1 must prove:

- successful detached mapping in both composition directions;
- failure and cancellation propagation in both directions;
- exact parent executable identity without fake Graph fields;
- Agent and Workflow Store isolation;
- independent limits and results;
- correct span parentage for both hybrid hierarchies;
- hook registration and unsubscription during a run cannot change that run's
  snapshot;
- cancellation during started and terminal hook dispatch follows the accepted
  terminal boundary without a second outcome;
- Agent failure and cancellation inside a Workflow Node, plus failure and
  cancellation inside a Workflow-backed Tool, retain both executable outcomes;
- shared explicit Hooks registries remain isolated by run;
- Workflow Tools receive per-call data through application-owned factories
  without mutating reusable Workflow definitions;
- the same Agent definition composes concurrently with both eligible reusable
  and per-call factory-created Workflows without state or observer-membership
  leakage.

Lifecycle refactoring must preserve existing Workflow behavior through current
tests except for the accepted callback-membership snapshot change. That change
is intentional, breaking, and requires coordinated public docs and tests.
Only graph assumptions that prevent a truthful Agent lifecycle should move.

## Consequences

Composition remains explicit and easy to diagnose. Applications retain mapping
and recovery policy, while Junjo preserves nested cancellation, failure, and
telemetry semantics.

The lifecycle layer requires a focused split between common, Graph, and Agent
identity. Some application mapping code will repeat during the proof, but that
repetition supplies evidence for any future adapter.

## Rejected alternatives

- Agent directly in a Graph: it gives a dynamic executable fake static
  structure.
- Generic AgentNode initially: input, dependencies, recovery, and Store actions
  are application policy.
- Generic WorkflowTool initially: Workflow construction and result mapping are
  application policy.
- Shared parent/child Store: it breaks isolated execution ownership.
- Fake or nullable Graph fields on Agent events: they weaken truthful contracts.
- Hooks inherited across nesting: it creates hidden observer behavior.
- Telemetry through hooks: optional callbacks cannot be the diagnostic control
  plane.
- Universal executable base class: concrete commonality is not yet proven.

## Deferred decisions

- generic Agent/Workflow adapters;
- direct Agent Graph membership;
- automatic Store mapping;
- cross-executable global budgets or deadlines;
- transaction and compensation policy;
- durable nesting and replay;
- public operation hooks;
- multi-agent delegation and parallel Tools;
- a universal executable protocol or base class.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0004: Agent ModelDriver and Tool contracts](0004-agent-model-driver-and-tool-contracts.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
