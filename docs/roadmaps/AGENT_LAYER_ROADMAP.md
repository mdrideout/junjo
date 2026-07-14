# Junjo Agent Layer Strategy And Roadmap

## Status

Strategy and implementation record. This roadmap records the current product
and architecture direction for autonomous Agent execution in Junjo. Accepted
ADRs, not this roadmap, own runtime and telemetry contracts.

Horizon 0 is complete as of 2026-07-13. The Horizon 1 Agent kernel, telemetry
contract version 2, and cohesive Studio trace-evidence path are implemented.
Horizon 2 remains in progress: its Turn, correlation, diagnostics, persistence,
and composition foundations exist, but the real AI-powered application and its
eval-driven-development loop have not been faithfully restored.

The remaining application work is governed by the
[AI Chat Product Restoration And Eval-Driven Development Plan](AI_CHAT_PRODUCT_RESTORATION_AND_EVAL_DRIVEN_DEVELOPMENT.md).
The independently versioned production cutover remains separate from the
runtime-design and product-restoration gates.

The completed Horizon 0 decision and sequencing record lives in
[AGENT_LAYER_PHASE_0.md](AGENT_LAYER_PHASE_0.md).

Before a horizon changes a strategic runtime contract, write or update the
relevant ADR and explicitly consider compatibility with Junjo AI Studio.

## Vision

Junjo should become an execution foundation where deterministic workflows and
autonomous agents share one coherent model for:

- isolated per-run execution
- typed state, inputs, and outputs
- explicit capabilities and side effects
- cancellation and failure handling
- lifecycle observation
- OpenTelemetry instrumentation
- deterministic testing
- probabilistic evaluation

Structured workflows remain the preferred tool for known, repetitive,
high-value procedures. Autonomous agents handle open-ended requests by deciding
which bounded capabilities and structured workflows to use.

The long-term product direction is to support user-shaped applications whose
data structures, workflows, and interfaces can evolve from user requests while
remaining inspectable, testable, versioned, and observable.

## Repository Roles

### Junjo

Junjo is the execution kernel.

It should own the reusable runtime concepts that let application developers
compose deterministic workflows and autonomous behavior without operating two
unrelated orchestration systems.

### AI Chat Example

`sdks/python/examples/ai_chat` is the first framework proving ground and
canonical teaching application for the Agent layer.

It proves that the public Junjo primitives are:

- useful in a realistic application
- effective for eval-driven development with live models
- observable through the Junjo telemetry contract
- understandable from public code and documentation
- compatible with structured Workflows and concurrent executions

Agent runtime behavior must be implemented in `sdks/python/src/junjo`, not
hidden inside the example. The example is an acceptance application for public
SDK behavior.

### Junjo AI Studio

Junjo AI Studio is the evidence and control plane.

It now visualizes and queries Agent execution evidence. Later horizons add
evaluation datasets, experiments, comparisons, failure analysis, and governed
improvement proposals.

Agent telemetry is part of the shared telemetry contract. Changes to span
semantics must update the SDK producer, canonical contract, and Studio consumer
conformance in one monorepo change.

### MBB Platform

MBB remains the vertical product proving ground.

It should adopt the Agent layer only after the core execution and telemetry
contracts have been proven in `sdks/python/examples/ai_chat`. MBB will then
validate whether the foundation creates a valuable personalized application,
including schema-aware questions, user-defined tracking, and adaptive
interfaces.

## Strategic Principles

### Workflows And Agents Are Complementary

Do not replace reliable Junjo workflows with a universal agent.

- A Workflow declares possible Graph paths and traverses one while models
  perform bounded steps.
- An Agent chooses the next capability at runtime and realizes an ordered
  operation sequence rather than a Graph path.
- An agent may call a workflow as a reliable tool.
- A workflow may execute an agent inside an explicitly bounded step.

The same application should be able to move a capability from exploratory agent
behavior into a structured workflow when the required procedure becomes known.

### The Agent Layer Is Not Another Provider SDK

Junjo should not rebuild the OpenAI Agents SDK, PydanticAI, or every model
provider client.

Junjo should own execution semantics and accept an injected ModelDriver that
translates between provider-specific APIs and Junjo's agent execution contract.
The application remains in control of provider selection and provider-specific
configuration.

### Definitions Are Reusable; Runs Are Isolated

An Agent definition should follow the same principle as `Workflow` and
`Subflow`: it is reusable configuration, not a live mutable run container.

Each agent execution should receive fresh run-local context and return a
detached result. Concurrent runs must not share mutable execution state.

### Side Effects Remain Explicit

The model may decide which tool to call. The tool implementation owns the
actual side effect.

Persistence, authorization, exact calculations, validation, and external API
operations should remain explicit application capabilities rather than being
hidden inside prompts.

### Dynamic Execution Is Not A Static Graph

A workflow has a predeclared graph. An agent produces a dynamic sequence of
model decisions and tool calls.

Do not misrepresent an Agent run as a static Workflow Graph. Junjo AI Studio
shows a dynamic Agent operation timeline, while nested Junjo Workflows retain
their normal Graph visualization.

### Deterministic Tests And Live Evals Are Separate

The default Junjo test suite must remain deterministic, hermetic, and runnable
without model API keys or Junjo AI Studio.

Live-model evaluations are valuable, but they are explicitly invoked
experiments rather than default CI tests.

### Prefer The Smallest Complete Runtime

The first Agent layer should prove one coherent execution loop before adding
multi-agent handoffs, persistent sessions, MCP, generated interfaces, durable
job execution, or automatic system modification.

## Target Composition Model

The corrective `ai_chat` target preserves the existing specialized Workflow
behavior, adds an Agent at the open-ended general-response boundary, and keeps
application-owned Turn admission:

```text
Receive request
  -> server admits a versioned Turn
  -> handle-message Workflow
       -> concurrently load bounded history and contact context
       -> assess the known directive
       -> branch to work, date, image Subflow, or general Agent response
       -> persist the outcome
  -> reconcile terminal Turn status and runtime references
  -> return the committed Turn
```

The chat agent may:

- answer directly
- call deterministic read/query tools
- invoke a structured Junjo workflow as a tool
- return a typed final result to the owning workflow

This proves both important composition directions:

```text
Workflow -> Agent
Agent -> Workflow Tool
```

The proof lives under `sdks/python/examples/ai_chat`. The general response path
proves Workflow-to-Agent execution. A bounded image Workflow Tool proves
Agent-to-Workflow composition without replacing the existing explicit image
Subflow or the specialized work and date paths.

## Accepted Runtime Responsibilities

ADRs 0003 through 0006 accept these responsibility boundaries. Horizon 1
implements them in the public Python Agent API; public docstrings and the
Sphinx API reference own exact signatures.

### Agent Definition

Reusable configuration describing:

- stable application-owned key
- name
- instructions
- declared input type
- ModelDriver binding
- available tools
- structured output type
- execution limits
- optional nonstructural lifecycle observer registry

### Agent Run Context

Read-only run identity and application dependencies made available to Tool
services without exposing or mutating private Agent state.

### ModelDriver

Injected boundary responsible for:

- sending model input to a provider
- exposing tool definitions in the provider's format
- translating model output into provider-neutral Junjo results
- reporting provider usage information when available
- supporting deterministic scripted test implementations

### Tool

A typed capability with:

- a stable name and useful description
- validated input
- explicit output
- an application-owned implementation
- failure and cancellation semantics
- telemetry around each execution

A Junjo workflow should be adaptable into a tool without erasing its normal
execution result or telemetry hierarchy.

### Agent Execution Result

A frozen, detached post-run result consistent with the role of
`ExecutionResult`. ADRs 0003 and 0004 require:

- Agent key, definition identity, structural identity, and run identity
- validated final typed output
- detached normalized transcript
- normalized provider-reported model usage
- model-request count and requested, admitted, started, and completed Tool-call
  counts
- `final_output` termination reason

Failure and cancellation do not return an output-less success.

## Testing And Evaluation Model

### Layer 1: Junjo Runtime Tests

SDK tests under `sdks/python/tests` use a scripted ModelDriver and
deterministic Tools.

They should cover at least:

- direct final output
- one and multiple tool-call iterations
- tool argument validation
- tool result propagation
- structured final output validation
- unknown tools and malformed model behavior
- tool failures
- model failures
- model-request and Tool-call limits
- usage accounting
- cancellation
- concurrent run isolation
- reusable Agent definitions
- detached execution results
- agent execution inside a workflow
- workflow execution as an agent tool
- lifecycle and OpenTelemetry hierarchy

These tests run in the normal Junjo CI gate.

### Layer 2: Minimal AI Chat Integrity Checks

The `ai_chat` backend keeps only deterministic checks for application startup,
Turn and versioned-object persistence invariants, transport integration, debug
configuration safety, and the small amount of deterministic application
machinery it owns. Agent execution semantics, failure matrices, concurrency,
and telemetry conformance remain SDK-owned tests.

Scripted model behavior must not be used to claim that AI Chat product quality
or historical functionality has been validated.

### Layer 3: AI Chat Live Evals

Live evaluations are the primary AI Chat product-development loop. They live
in explicit, colocated `evals/` surfaces and require an explicit command and
provider credentials.

Candidate evaluation dimensions include:

- correct tool selection
- correct workflow selection
- grounded use of conversation context
- final answer quality
- persona consistency
- unnecessary tool calls
- completion cost and latency
- behavior across model or prompt changes

Pytest remains the runner, but live evals are selected deliberately rather than
being collected with the hermetic SDK suite. Evaluate real Junjo executables
through supported execution methods. Add only the smallest public Node eval
execution helper needed to preserve normal lifecycle and telemetry; application
code continues to own datasets, judges, rubrics, and promotion policy.

### Layer 4: Production Evidence And Replay

Later, Studio should turn representative production executions into evaluation
cases, support comparisons across artifact versions, and record experiment
results. This layer is not required for the first Agent proof.

## Telemetry Direction

The Agent layer produces enough semantic telemetry to reconstruct:

- the overall agent run
- each model request and response boundary
- available and selected tools
- tool inputs, outputs, failures, and duration
- workflow executions invoked as tools
- usage and limit information
- cancellation and terminal status

The telemetry contract should preserve the hierarchy of a hybrid run:

```text
Workflow span
  -> Node span
      -> Agent span
          -> Model operation span
          -> Tool operation span
              -> Nested Workflow span
                  -> Node spans
          -> Model operation span
```

ADR 0006 accepts telemetry contract version 2: Agent is an executable with
`junjo.span_type = "agent"`, while model and Tool spans are ordered operations
identified by `junjo.agent.operation_type`. Store transitions gain monotonic
sequence and revision fields. Canonical fixtures, the SDK producer, and Studio
ingestion/backend/frontend consumers change atomically.

Payload modes are an explicit contract seam in ADR 0006. The Horizon 1 Python
producer uses the built-in `junjo.full.v1` policy for Workflow and Agent
evidence; custom selection plus production privacy and retention policy remain
deferred until the core mechanics prove value.

## Horizons

Horizons describe capability maturity, not promised release dates. Work should
not advance merely because the previous horizon has code; it should advance
when the previous horizon's exit criteria are satisfied.

### Horizon 0: Architecture And Contract Decisions

Status: Complete.

#### Objective

Define the smallest coherent Agent runtime and its relationship to existing
Junjo execution concepts.

#### Required decisions

- Agent as a first-class executable versus an adapter around `Node`
- reusable definition and run-local context ownership
- model-driver request and response contract
- tool definition and invocation contract
- structured output and result contract
- workflow-as-tool behavior
- agent-inside-workflow behavior
- cancellation, failure, and limit semantics
- streaming boundaries
- conversation history ownership
- lifecycle and telemetry semantics
- deterministic testing support

#### Exit criteria

- [x] Root ADRs 0003 through 0006 and Studio ADRs 004 and 007 are accepted.
- [x] The initial public surface and explicit non-goals are understood.
- [x] Shared telemetry-contract and Studio consumer impact is documented.
- [x] The `ai_chat` acceptance scenarios are defined.

### Horizon 1: Deterministic Agent Kernel And Evidence Path

Status: Complete as of 2026-07-14. The independently versioned production
cutover remains pending.

#### Objective

Implement a single-Agent Tool loop and its complete shared diagnostic path as
normal Junjo platform capabilities.

#### Scope

- reusable Agent definition
- isolated run execution
- injected ModelDriver
- typed application Tools
- structured final output
- bounded model requests and Tool calls
- usage accounting
- typed input validation
- cancellation and failures
- detached execution result
- lifecycle identity and snapshotted observer dispatch
- Workflow -> Node -> Agent and Agent -> Tool -> Workflow composition
- scripted ModelDriver for tests
- telemetry contract version 2 schemas and canonical fixtures
- Agent and Store-revision telemetry producer conformance
- Studio ingestion preservation and semantic Agent queries
- Studio backend Store reconstruction and evidence integrity
- Studio dynamic Agent timeline and verified state navigation
- public Agent docstrings and Sphinx concepts/API documentation
- deterministic testing and telemetry conformance guidance

#### Explicit non-goals

- multi-agent handoffs
- persistent conversation sessions
- MCP integration
- generated workflows or interfaces
- automatic prompt or source modification
- durable background execution
- incremental public streaming

#### Exit criteria

- [x] All runtime behavior is covered by deterministic SDK-owned tests under
  `sdks/python/tests`.
- [x] Concurrent executions demonstrate state isolation.
- [x] Failure and cancellation behavior is explicit and observable.
- [x] Both composition directions prove success, failure, cancellation, independent
  Stores and limits, and truthful parentage.
- [x] Contract version 2 producer fixtures prove SDK conformance; all valid and
  invalid fixture sets prove Studio consumer behavior.
- [x] Studio reconstructs standalone and hybrid Agent executions without a fake
  Graph.
- [x] Public docs explain construction, execution, composition, deterministic
  testing, failure/cancellation, and telemetry without calling an Agent a
  dynamic Graph.
- [x] The greenfield release runbook defines the intentional producer-first
  cutover and temporary semantic-diagnostics outage without dual support.
- [x] No model provider or external service is required to run validation.

#### Production cutover gate

- [ ] Publish Python SDK `0.65.0`, then Studio `0.82.0` or newer with the
  canonical VM/Caddy SDK pin and both deployment compatibility statements
  updated to `0.65.0`; publish generated mirrors in that Studio release.

### Horizon 2: AI Chat Hybrid Execution Proof

Status: In progress. Turn, correlation, persistence, Studio resolution, and
composition foundations are implemented; faithful product restoration and the
live eval-driven proof remain incomplete.

#### Objective

Prove that the Agent layer composes cleanly with a realistic Junjo application.

#### Scope

- structured Workflow shell around the chat Agent
- live model-powered contact creation and specialized response Nodes
- read-only conversation and contact tools
- at least one Junjo workflow exposed as an agent tool
- typed final result persisted by application-owned logic
- application-owned live eval datasets and judges
- minimal deterministic application integrity checks
- a clear runnable example and teaching narrative

#### Exit criteria

- [ ] All nine canonical
  [Initial AI Chat Acceptance Scenarios](#initial-ai-chat-acceptance-scenarios)
  pass with the restored live application behavior.
- [ ] Contact, directive, persona, response, image, and Agent quality are
  measured through real-provider evals.
- [ ] The example uses only public Junjo runtime APIs, including a supported
  Node eval execution surface.
- [x] The example no longer relies on timing sleeps or untracked execution for its
  canonical agent path.
- [ ] The
  [product restoration plan](AI_CHAT_PRODUCT_RESTORATION_AND_EVAL_DRIVEN_DEVELOPMENT.md)
  passes in full.

### Horizon 3: Studio Eval Measurement And Comparison

Horizon 2 restores application-owned live evals as a core AI Chat development
practice. Horizon 3 builds platform-level measurement and comparison on top of
that working eval-and-evidence loop.

#### Objective

Make autonomous behavior measurable without weakening deterministic CI.

#### Scope

- opt-in live evaluation layout
- initial tool-selection and response-quality datasets
- model and prompt comparison workflow
- deterministic score and report helpers where possible
- links from evaluation results to exact execution and artifact evidence
- explicit cost, latency, and quality comparison reports

#### Exit criteria

- Live evals require explicit invocation and credentials.
- Deterministic tests and probabilistic evals have separate commands and
  documentation.
- Evaluation results identify the exact Agent structural ID, service version,
  model identity, and dataset version.
- Probabilistic results never become a required default CI gate.

### Horizon 4: Agent-Queryable Evidence Plane

#### Objective

Allow agents and developers to query execution evidence semantically rather
than reading physical span storage.

#### Scope

- execution search by workflow, agent, version, time, and outcome
- execution-tree retrieval
- state-timeline reconstruction
- tool and model-call queries
- representative success and failure sampling
- evaluation datasets and cases
- experiment records and version comparisons
- programmatic Studio API and later MCP access where useful

#### Exit criteria

- An analysis agent can find a failure cohort and retrieve the evidence needed
  to evaluate it.
- Studio remains the owner of physical telemetry storage and query mechanics.
- Evaluation results link back to the exact execution and artifact versions.

### Horizon 5: Versioned Object And Schema Substrate

#### Objective

Prove a logical persistence model that supports user-defined data without
making SQL DDL migrations the product-development bottleneck.

#### Scope

- versioned schema registry
- versioned JSON objects and immutable revisions
- provenance and artifact-version references
- schema-aware read and write tools
- explicit transformation and compatibility rules
- rebuildable SQL, analytical, search, or vector projections

This should first be proven in a bounded MBB tracking capability. The logical
object contract matters before choosing permanent physical storage.

#### Exit criteria

- A user-defined tracked concept can be added without a SQL DDL migration.
- Historical objects remain interpretable through explicit schema versions.
- Exact filtering, aggregation, and authorization use deterministic query
  capabilities.
- Derived indexes can be rebuilt from canonical objects.

### Horizon 6: Versioned Experience Configuration

#### Objective

Allow a user request to produce an inspectable and reversible application
experience revision.

#### Scope

- versioned experience definition
- logical data schemas
- capture and processing workflows
- trusted UI component catalog and declarative view specifications
- change preview, activation, and rollback
- configuration agent with bounded artifact-writing authority

#### Exit criteria

- A bounded user request can create a useful new tracker and view.
- Generated artifacts are versioned and attributable.
- Activation does not destroy or silently reinterpret historical data.
- The user can refine or roll back the experience.

### Horizon 7: Governed Recursive Improvement

#### Objective

Use production evidence and evals to propose and validate improvements
programmatically.

#### Scope

- automated failure-cohort discovery
- evaluation-case generation from real executions
- candidate prompt, workflow, schema, Agent, and UI revisions
- historical replay and regression comparison
- quality, cost, and latency gates
- promotion and rollback policies

Source-code changes should remain a separate coding-agent workflow until
configuration-level improvement is proven.

#### Exit criteria

- The system can produce a candidate change with traceable evidence.
- The candidate is tested against historical and regression cases.
- Promotion decisions and rollback targets are explicit.
- Improvement claims are tied to measured outcomes rather than self-judgment
  alone.

## Initial AI Chat Acceptance Scenarios

The first proof should remain deliberately small.

1. A general conversation request produces a direct final response.
2. A question about conversation history calls a deterministic query tool.
3. An image request calls a structured Junjo workflow tool.
4. A malformed tool call is rejected predictably.
5. A tool failure is surfaced with correct Agent and Workflow failure behavior.
6. A looping model is stopped by an explicit limit.
7. Cancellation drains the active model/tool/workflow work correctly.
8. Concurrent chat executions do not share run-local state.
9. The complete hybrid hierarchy is visible in in-memory telemetry and Studio.

## Deferred Decisions

Do not settle these until the earlier horizons provide evidence:

- multi-agent manager versus handoff APIs
- long-lived session persistence
- durable execution infrastructure
- MCP client and server surfaces
- declarative executable workflow specifications
- physical object-storage technology
- automated promotion authority
- general-purpose generated UI protocol
- packaging the Agent layer separately from the main `junjo` distribution

## Success Definition

The Agent layer succeeds when Junjo application developers can choose the right
execution mode per responsibility:

- deterministic workflows for known procedures
- autonomous agents for open-ended capability selection
- agents inside bounded workflow steps
- workflows as reliable agent tools

All four paths must remain isolated per run, transparent in telemetry,
deterministic to test, and suitable for application-owned evaluation.

The long-term Junjo advantage is not merely that an agent can call tools. It is
that an agent can improvise, a workflow can guarantee, state can evolve,
telemetry can explain, and evaluation can determine whether the complete system
is actually improving.
