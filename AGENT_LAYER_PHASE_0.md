# Agent Layer Phase 0: Architecture And Telemetry Design

## Status

Proposed implementation-planning document.

This document turns Horizon 0 from `AGENT_LAYER_ROADMAP.md` into a concrete
architecture discussion. It records recommended boundaries, contracts,
telemetry requirements, Junjo AI Studio implications, open decisions, and the
ADRs that should be accepted before Agent runtime implementation begins.

This document is not itself an accepted ADR and does not define a final public
API.

Repository consolidation is planned separately in
`MONOREPO_MIGRATION_PLAN.md`. The ADR paths and numbers suggested below are
provisional until the monorepo ownership structure is accepted.

## Phase 0 Objective

Define the smallest coherent autonomous Agent runtime that can be built on
Junjo's existing architectural principles without weakening the clarity of the
Workflow, Graph, State, Store, Execution, Lifecycle, Hook, and Telemetry layers.

The design must make every realized Agent execution diagnostically transparent
in Junjo AI Studio, including:

- Agent definition and run identity
- exact normalized model inputs and outputs, subject to an explicit payload
  policy
- tools made available to the model
- tool calls selected by the model
- validated tool arguments and returned results
- Agent run state before, during, and after execution
- chronological state transitions and JSON patches
- nested Junjo Workflow executions invoked by tools
- model and tool usage
- failures, cancellation, and termination reason

Phase 0 is complete when the strategic decisions are accepted and the paired
SDK/Studio telemetry contract is specific enough to implement and test.

## Architectural Position

An Agent is a reusable executable definition that delegates next-step selection
to a model within a bounded loop over explicit tools and produces a typed,
detached result.

An Agent should be a first-class executable sibling to `Workflow`. It should not
subclass `Workflow`, `Subflow`, or `Node`.

The Agent runtime should reuse Junjo's proven principles:

- reusable definitions and isolated executions
- fresh run-local state for every execution
- immutable state transitions
- explicit side effects
- detached public results
- cancellation distinct from failure
- lifecycle hooks as optional observers
- telemetry independent from hooks
- application-owned persistence and transport

It should not reuse graph-specific contracts when those contracts would
misrepresent dynamic Agent behavior.

## What Agent Owns

The reusable Agent definition owns configuration:

- definition identity
- human-readable name
- instructions
- model driver
- available tools
- expected final output type
- explicit execution limits
- optional Agent lifecycle hooks

Each Agent execution owns run-local mechanics:

- run identity
- input
- supplied conversation history
- internal transcript
- run-local dependencies
- model request count
- tool call count
- usage totals
- pending and completed tool calls
- final output
- termination reason
- lifecycle and telemetry context

## What Agent Does Not Own

Agent must not own:

- persistent chat or conversation storage
- long-term memory storage
- application database sessions
- user authentication or authorization policy
- product event transport
- WebSocket or HTTP lifecycle
- provider API keys as global Agent state
- background job durability
- arbitrary application state outside explicit tools
- automatic source-code modification
- eval datasets or promotion policy
- Junjo AI Studio persistence or queries

Applications pass dependencies and selected context into an Agent execution.
Applications decide what parts of the result or transcript to persist.

## Layer Boundaries

### Public Definition Layer

The public layer should expose simple, explicit construction of:

- Agent
- Tool
- model-driver contract
- Agent execution result
- Agent lifecycle hooks

Public construction should not require decorators, docstring parsing, hidden
global registries, or provider-owned conversation sessions.

### Execution Layer

A private Agent execution layer should own the bounded model/tool loop. It is
the only layer permitted to mutate internal Agent run state.

Conceptual execution:

```text
create fresh run context and Agent state
  -> record initial state
  -> construct normalized model request
  -> execute model driver
  -> record normalized model response
  -> final output?
       yes -> validate output -> complete
       no  -> validate ordered tool calls
              -> execute tools
              -> record tool results
              -> repeat
```

The model chooses the next action. Junjo owns validation, execution, state,
limits, cancellation, results, lifecycle, and telemetry.

### Agent State Layer

Agent execution needs a Junjo-owned internal state model and store. Application
developers should not need to define an Agent store for ordinary use.

Candidate Agent run state responsibilities:

- normalized input and prior history
- ordered model and tool transcript
- current model iteration
- total tool calls
- accumulated usage
- pending tool calls
- completed tool results
- validated final output
- termination reason

State changes should happen through explicit store actions such as:

- append model response
- register pending tool calls
- append tool result
- update usage
- set final output
- set termination reason

The exact state model requires an ADR because it becomes part of telemetry,
diagnostics, deterministic testing, and `AgentExecutionResult` design.

### Dependency Layer

Application dependencies are not Agent state.

Dependencies may include:

- authenticated user context
- repositories
- database or HTTP clients
- storage clients
- application configuration
- request-scoped domain event sinks

Tools receive an opaque typed run context containing those dependencies. The
model sees only values deliberately included in model input or returned by a
tool.

This preserves three separate concepts:

```text
Agent state
  = information evolving during one Agent execution

Application dependencies
  = services available to perform work

Model context
  = selected information intentionally shown to the model
```

### Model Driver Layer

The model driver owns provider translation, not Agent orchestration.

Junjo supplies a normalized request containing:

- instructions
- input and transcript
- available tool definitions
- expected final output schema
- explicitly standardized model configuration

The driver returns one normalized response:

- typed final-output candidate, or
- one or more ordered tool calls

Each normalized tool call includes:

- provider tool-call identifier
- tool name
- JSON arguments

The driver owns:

- provider SDK calls
- provider request and response conversion
- provider-specific errors
- provider usage extraction
- provider streaming assembly when supported later

Junjo owns:

- the execution loop
- transcript state
- tool resolution and validation
- limits
- output validation
- cancellation
- lifecycle
- result construction
- Junjo semantic telemetry

### Tool Layer

A Tool is an explicit model-callable capability.

A Tool contract should include:

- stable name
- clear description
- validated input type
- explicit output contract
- application-owned service callable

The Tool service receives validated input and the typed Agent run context.

Default error semantics should be explicit:

- a tool exception fails Agent execution
- a recoverable domain result is returned as a typed Tool result
- Junjo does not silently convert arbitrary exceptions into model-visible text
- model-visible recovery behavior may be added later only as an explicit policy

The initial implementation should execute multiple Tool calls sequentially in
the order returned by the model. Concurrency can be added later as an explicit
policy once read-only and mutating Tool semantics are represented.

## Workflow And Agent Composition

### Workflow Executes Agent

An application Node can read its Workflow Store, execute an Agent, and commit
selected results back through Store actions.

```text
Application Node
  -> read detached Workflow state
  -> construct Agent input and dependencies
  -> execute Agent
  -> validate AgentExecutionResult
  -> update Workflow Store
```

The first implementation should use an ordinary application Node rather than a
generic `AgentNode` adapter. Introduce an adapter only if repeated mapping code
becomes brittle.

### Agent Executes Workflow

A Tool service can construct and execute a Junjo Workflow, then map its detached
`ExecutionResult` into a Tool result.

```text
Tool service
  -> construct Workflow definition and run-local input
  -> execute Workflow
  -> map ExecutionResult into typed Tool output
```

The first implementation should use explicit application code rather than a
generic Workflow-to-Tool adapter. OpenTelemetry parentage should naturally place
the nested Workflow span beneath the Tool span.

## Lifecycle Architecture

### Current Constraint

Junjo's current internal lifecycle context is graph-shaped.
`StoreLifecycleContext` contains:

- enclosing Graph structural identity
- executable structural identity
- compiled Node structural IDs

Those fields are correct for Workflow Stores but do not cleanly describe a
standalone Agent.

The existing public `LifecycleEvent` also assumes Graph structural fields are
available for every event.

### Recommended Direction

Separate genuinely common execution identity from Graph-specific identity.

Conceptually:

```text
Executable identity
  - definition ID
  - runtime ID
  - name
  - executable type
  - parent executable runtime ID

Graph executable identity
  - executable structural ID
  - enclosing Graph structural ID
  - parent executable structural ID
```

Do not use fake Graph IDs for Agent execution. Do not make every existing field
nullable without first considering whether separate event bases and lifecycle
contexts would preserve clearer contracts.

Agent lifecycle should include:

- Agent started
- Agent completed
- Agent failed
- Agent cancelled

Public hooks remain optional observers. Hook failure must not control Agent
execution, and hook errors should be recorded on the real active Agent span in
the same manner as existing Workflow and Node hook failures.

Model and Tool operations require telemetry but do not necessarily require
public hooks in the first implementation.

## Telemetry Principles

### Telemetry Is The Diagnostic Source Of Truth

Junjo telemetry must make it possible to reconstruct what the Agent was asked,
what capabilities it had, what it chose, what each capability returned, how
state changed, and why execution terminated.

Public hooks must not be the telemetry control plane.

### Full Transparency Has A Defined Boundary

Full transparency means recording observable execution evidence:

- normalized instructions and model input
- available Tool definitions
- normalized model output
- selected Tool calls
- Tool arguments and results
- state transitions
- usage and timing
- errors and cancellation

It does not mean requiring or fabricating hidden model chain-of-thought. If a
provider returns an explicit reasoning summary as ordinary output, it may be
recorded according to payload policy. Junjo diagnostics must not depend on
private reasoning tokens that providers do not expose.

### Agent Runs Are Dynamic Traces

A Workflow has a serialized execution Graph snapshot. An Agent does not.

Agent execution should be represented through the realized OpenTelemetry span
tree and ordered state events. Junjo AI Studio should render an Agent decision
timeline or tree, not a fabricated static Graph.

Nested Workflows invoked by Tools retain their own Graph snapshots and Graph
views.

### Existing State Event Contract Should Be Reused

The current `BaseStore.set_state()` contract emits `set_state` events containing:

- event ID
- Store name and ID
- Store action
- JSON Patch

Junjo AI Studio already groups and renders state events by Store ID and applies
the patches chronologically. Agent state should reuse this contract so Studio's
state-diff machinery remains conceptually consistent.

The Agent telemetry ADR should decide whether the generic state contract also
adds monotonic Store revision information:

- revision before
- revision after
- deterministic transition sequence

Timestamps remain useful, but an explicit revision gives Studio a stable total
ordering and supports future concurrent execution without ambiguous state-event
order.

### State Transitions Should Remain Causally Attached

State changes should be recorded on the span that caused them:

- model response state changes on the active model-operation span
- Tool-call registration on the active Agent/model span
- Tool result state changes on the active Tool span
- final-output state changes on the active Agent or final model span

Studio can then aggregate all `set_state` events by Agent Store ID while also
showing which operation caused each transition.

## Proposed Span Hierarchy

```text
Agent span
  -> model request span: iteration 1
  -> Tool span: query_history
  -> model request span: iteration 2
  -> Tool span: create_image
      -> Workflow span: Create Image Workflow
          -> Node spans
  -> model request span: iteration 3
```

When an Agent runs inside a Workflow Node:

```text
Workflow span
  -> Node span: Run Chat Agent
      -> Agent span
          -> model and Tool spans
```

OpenTelemetry span parentage is the runtime execution hierarchy. Junjo runtime
and structural attributes provide semantic identity within that hierarchy.

## Proposed Telemetry Semantics

Exact names must be accepted in the Agent telemetry ADR. The following groups
describe the required information and candidate attribute names.

### Agent Span

Generic executable attributes:

- `junjo.span_type = "agent"`
- `junjo.executable_definition_id`
- `junjo.executable_runtime_id`
- parent executable runtime identity when nested

Agent-specific attributes:

- `junjo.agent.definition_snapshot`
- `junjo.agent.structural_id` or explicit definition version
- `junjo.agent.store.id`
- `junjo.agent.state.start`
- `junjo.agent.state.end`
- `junjo.agent.model_request.count`
- `junjo.agent.tool_call.count`
- `junjo.agent.termination_reason`
- accumulated usage fields

The Agent definition snapshot should be canonical, versioned JSON containing
the exact diagnosable definition for the run, subject to payload policy:

- snapshot schema version
- Agent name and identity
- static instructions
- model-driver/model identity
- available Tool names and descriptions
- Tool input and output schemas
- final output schema
- execution limits

The snapshot should support a deterministic structural fingerprint so Studio
can compare runs using materially different Agent definitions.

### Model Operation Span

Model and Tool operations should not automatically be treated as Graph
executables. A separate operation attribute may be clearer than adding every
operation to `JunjoOtelSpanTypes`.

Candidate information:

- `junjo.agent.operation_type = "model_request"`
- Agent run ID
- iteration ordinal
- Agent state revision used to construct the request
- provider and model identity
- normalized request JSON
- normalized response JSON
- response type: final output or Tool calls
- input, output, cached, and reasoning-token usage when supplied by the provider
- request duration and terminal status

The normalized request must preserve the actual semantic content sent through
the driver. Provider instrumentation may add additional provider-specific spans,
but Junjo must not depend on provider instrumentation for its Agent diagnostic
contract.

### Tool Operation Span

Candidate information:

- `junjo.agent.operation_type = "tool"`
- Agent run ID
- Tool definition identity or structural fingerprint
- Tool name
- provider Tool-call ID
- call ordinal
- validated argument JSON
- serialized result JSON
- Agent state revision before and after result commit
- success, failure, or cancellation

A nested Workflow invoked by the Tool should be a normal child span rather than
having its telemetry copied into Tool attributes.

### Errors And Cancellation

Agent, model, Tool, and nested Workflow spans should use the existing Junjo and
OpenTelemetry conventions:

- standard error status and `error.type` for failures
- recorded exception event where appropriate
- `junjo.cancelled = true` for cancellation
- `junjo.cancelled_reason`

Cancellation should not be represented as an error.

## Payload Size And Duplication

Full diagnostics can produce large telemetry payloads, especially when full
conversation history is repeated on every model request.

The telemetry ADR must explicitly choose how exact reproducibility is balanced
against duplication. Candidate strategy:

- Agent state start plus ordered JSON patches reconstruct the transcript
- Agent definition snapshot records offered capabilities once per run
- each model span records the exact normalized request or an exact delta plus
  the referenced Agent state revision
- Tool spans record exact arguments and results once
- large binary data is represented by metadata or application-owned references,
  not embedded directly in span attributes

Do not silently truncate payloads inside execution mechanics. Any redaction,
exclusion, reference substitution, or size limit should be implemented through
an explicit payload policy with observable metadata indicating that the value
was transformed.

## Junjo AI Studio Requirements

### Ingestion

The Rust ingestion service currently preserves span attributes and events as
JSON. Agent telemetry should continue using standard OTLP spans and events so
ingestion remains primarily transport and durable storage rather than an Agent
semantic processor.

Ingestion contract tests should prove preservation of:

- Agent span attributes
- model-operation attributes
- Tool-operation attributes
- Agent `set_state` events
- failure and cancellation evidence

### Backend

The backend should expose semantic Agent queries without requiring clients to
scan raw span storage.

Initial diagnostic queries should support:

- list Agent executions by service and Agent identity
- retrieve the complete trace for an Agent run
- retrieve standalone and Workflow-nested Agent runs
- filter by completion, failure, or cancellation
- retrieve model and Tool child operations
- retrieve Agent state events by Store ID

The metadata index may eventually add Agent-specific file-selection hints, but
Agent ingestion must not become coupled to backend availability.

### Frontend

Junjo AI Studio should add an Agent execution view with:

- Agent definition and available capabilities
- input and final output
- chronological model and Tool timeline
- per-operation inputs and outputs
- state transition navigation
- before, after, patch, and detailed state views
- nested Workflow links and Graph visualization
- usage, duration, and termination summary
- failures and cancellation at the owning operation

Existing state-diff behavior should be reused through the `set_state` and Store
ID contract rather than implementing a second Agent-only diff engine.

The current frontend span accessor, schemas, state selectors, and Graph matching
logic are direct compatibility consumers of the SDK telemetry contract. Agent
fixtures must exercise those boundaries.

## Testing And Contract Verification

### Junjo SDK Tests

Use an OpenTelemetry in-memory exporter to assert the complete semantic contract
for deterministic scripted Agent executions.

Required cases:

- direct final output
- one Tool call followed by final output
- multiple ordered Tool calls
- Tool invoking a nested Workflow
- model failure
- Tool failure
- malformed model output
- limit termination
- cancellation during model execution
- cancellation during Tool execution
- Agent inside a Workflow Node
- concurrent Agent run isolation
- every Agent state patch reconstructs the final state

Tests should assert span hierarchy, identities, attributes, events, statuses,
and cancellation semantics.

### Paired Studio Fixtures

Create stable OTLP/JSON fixtures from representative deterministic Agent runs.
Junjo AI Studio tests should verify:

- ingestion preserves the contract
- backend queries return the complete Agent execution
- frontend schemas accept the payload
- timeline construction preserves execution order
- Agent state reconstruction reaches the expected final state
- nested Workflow spans still match their Graph snapshots
- failures and cancellations appear on the correct operation

### AI Chat Acceptance Application

The `examples/ai_chat` proof should include:

- a general response with no Tool
- a deterministic conversation-history query Tool
- a structured image Workflow invoked as a Tool
- a Tool failure
- bounded loop termination
- a complete Agent state and operation timeline in Studio

The example consumes public Junjo APIs. It must not contain runtime behavior that
belongs in `src/junjo`.

## Suggested Implementation Layers

File names remain implementation choices, but responsibilities should stay
visibly separated:

```text
public Agent definition and result
public model-driver contract and normalized message types
public Tool contract
private Agent execution loop
private Agent run state and Store
private Agent lifecycle dispatch
Agent telemetry attribute/schema definitions
provider drivers outside the core Agent execution layer
```

Do not introduce a universal executable superclass during Phase 0. Share small,
proven internal mechanisms only where Workflow and Agent genuinely repeat the
same behavior.

## Implementation Work Packages

### Work Package 1: Accept ADRs

Write and approve the Agent execution, model/Tool boundary, composition, and
telemetry ADRs before runtime implementation.

### Work Package 2: Prepare Common Lifecycle Boundaries

Refactor only the graph assumptions that prevent a clean Agent lifecycle.
Preserve Workflow, Node, Subflow, Store, Hook, and telemetry behavior with
existing tests before adding Agent behavior.

### Work Package 3: Implement Deterministic Agent Kernel

Implement reusable Agent definitions, isolated execution, internal immutable
state, normalized model responses, sequential Tool execution, explicit limits,
detached results, failure, and cancellation.

### Work Package 4: Implement Agent Telemetry With The Kernel

Telemetry is not a follow-up feature. Agent state, model, Tool, error, and
cancellation evidence must be emitted and tested as each execution behavior is
implemented.

### Work Package 5: Add Paired Studio Contract Support

Add ingestion fixtures, backend semantic queries, frontend schemas/accessors,
Agent timeline UI, state reconstruction, and nested Workflow visualization.

### Work Package 6: Prove The Public API In AI Chat

Update the example only after the runtime public surface is coherent and
deterministically tested.

### Work Package 7: Complete Public Teaching Surfaces

Update together:

- public docstrings
- Sphinx concepts and API docs
- deterministic test guidance
- opt-in eval guidance
- AI Chat README and runnable behavior
- Junjo/Studio paired-version compatibility notes

## Suggested ADR Set

The repository does not currently have a root Junjo ADR directory. When Phase 0
decisions are ready for acceptance, create `docs/adr/` and use it as the
strategic source of truth for these decisions.

### `docs/adr/0001-agent-execution-model.md`

Owns:

- definition of an Agent
- Agent as a first-class executable sibling to Workflow
- reusable definition and run-local execution boundary
- internal immutable Agent state
- detached Agent execution result
- limits, failures, cancellation, and termination
- why Agent is not a Node, Workflow, Subflow, session, or persistence layer

### `docs/adr/0002-agent-model-driver-and-tool-contracts.md`

Owns:

- provider-neutral model request and response contract
- application-owned provider drivers
- Tool definition, validation, execution, and result contract
- dependency context separate from state and model context
- sequential initial Tool policy
- strict default error semantics
- explicit non-goals for provider SDK recreation

### `docs/adr/0003-agent-workflow-composition.md`

Owns:

- Workflow executing Agent through an application Node
- Agent invoking Workflow through an application Tool
- state/input/output mapping ownership
- nested cancellation and failure propagation
- why generic adapters are deferred until repetition is proven
- OpenTelemetry parentage expectations

### `docs/adr/0004-agent-telemetry-contract.md`

Owns the SDK emission contract:

- Agent, model-operation, and Tool-operation span semantics
- executable and operation identity
- Agent definition snapshot and structural fingerprint
- Agent state start/end and `set_state` event behavior
- state revision and ordering decision
- normalized model request and response evidence
- Tool arguments and results
- usage, errors, cancellation, and termination
- payload size and payload-policy seam
- fixtures and paired compatibility requirements

This ADR should be reviewed against Junjo AI Studio before acceptance.

### Junjo AI Studio: `docs/adr/005-agent-execution-diagnostics.md`

Owns Studio interpretation and product behavior:

- Agent execution query model
- dynamic timeline/tree instead of static Graph rendering
- Agent state reconstruction
- nested Workflow Graph navigation
- backend semantic endpoints
- ingestion preservation tests
- frontend schemas, accessors, and diagnostics UI
- paired SDK/Studio fixture ownership

The Studio ADR references the SDK telemetry ADR instead of duplicating emitted
attribute definitions.

### Testing Strategy Document, Not ADR

Deterministic tests, live eval commands, dataset layout, and CI commands are
implementation and contributor workflow concerns. Keep them in testing docs
unless a strategic architectural decision emerges that requires an ADR.

## Recommended Initial Decisions

The Phase 0 discussion currently supports these defaults:

1. Agent is a first-class executable sibling to Workflow.
2. Agent definitions are reusable; every execution is isolated.
3. Agent owns no persistent memory, application transport, or database.
4. Internal Agent state follows Junjo's immutable Store pattern.
5. Dependencies remain separate from Agent state and model context.
6. Model drivers translate providers; Junjo owns orchestration.
7. Tools are explicit typed capabilities with application-owned services.
8. Tool calls execute sequentially and preserve model-returned order initially.
9. Tool exceptions fail execution by default.
10. Workflows and Agents compose through ordinary application Nodes and Tools
    before generic adapters are considered.
11. Agent lifecycle, application streaming, and telemetry remain separate.
12. Agent diagnostics use dynamic span hierarchy and ordered state events, not
    a fabricated Graph snapshot.
13. Agent telemetry is implemented and tested with the runtime, not afterward.
14. Junjo and Junjo AI Studio ship Agent telemetry changes as a paired contract.

## Open Decisions Requiring ADR Resolution

- final public execution method name and signature
- exact normalized input and transcript types
- exact structured-output validation and correction policy
- whether explicit output-validation retries exist initially
- exact Agent state exposed in `AgentExecutionResult`
- how Agent definition identity remains comparable across process restarts and
  releases
- exact common versus Graph-specific lifecycle context split
- public Agent hook surface
- model and Tool operation attribute namespace
- exact state revision contract
- exact model request storage versus reconstructable delta strategy
- initial payload-policy interface
- whether provider-specific drivers live in Junjo, optional packages, examples,
  or application code

## Phase 0 Exit Criteria

Phase 0 is complete when:

- the four Junjo ADRs are accepted
- the paired Studio diagnostics ADR is accepted
- Agent ownership and non-ownership boundaries are explicit
- Agent state, dependency, model-driver, Tool, and result contracts are defined
- Workflow/Agent composition is defined without premature adapters
- lifecycle refactoring scope is known
- Agent telemetry attributes, events, ordering, and span hierarchy are defined
- payload reconstruction and size strategy is defined
- deterministic SDK telemetry fixtures are specified
- paired Studio fixture and UI expectations are specified
- AI Chat acceptance scenarios and validation gates are agreed

Only then should Horizon 1 runtime implementation begin.
