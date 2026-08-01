# ADR 0013: SDK-orchestrated, application-executed Studio evaluations

- Status: Accepted
- Date: 2026-07-27
- Owners: Junjo platform
- Correction: Replaces the unshipped, same-day draft that assigned generic
  evaluation mechanics to AI Chat and excluded them from the Junjo SDK.

## Context

Junjo applications already execute Nodes, Workflows, and Agents through the
public runtime and export complete supported trace evidence to Junjo AI Studio.
Only the application process can faithfully construct the application's
providers, dependencies, Stores, prompts, domain types, and external services.
Studio cannot reconstruct those concerns from telemetry and must not become a
remote source executor.

That execution boundary does not mean each application should implement its own
evaluation system. Dataset and run DTOs, Studio transport, retry and resume
rules, execution binding, target and evaluator contracts, evaluation context,
revision capture, and command-line orchestration are Junjo product mechanics.
Putting them in AI Chat would make the reference application a second
framework, force every application to copy policy-sensitive code, and leave a
coding agent without a stable batteries-included interface.

Junjo therefore needs one framework that coordinates application-local
execution with Studio's shared control and evidence plane. It must let a
developer or coding agent run one immutable input set against multiple source
revisions and query each result beside the exact telemetry Studio received.

This decision builds on:

- ADR 0007's separation of domain, execution, and physical telemetry identity;
- ADR 0010's faithful one-Node execution envelope; and
- ADR 0012's trace-only Studio integration.

## Decision

### The Junjo SDK owns the evaluation framework

The Junjo Python distribution owns the complete reusable evaluation surface:

- typed Studio client, authentication support, DTOs, and typed errors;
- dataset, case, run, attempt, result, comparison, and evidence operations;
- target declarations for supported Node, Workflow, Agent, and application-flow
  execution shapes;
- evaluator interfaces, result contracts, composition, and common evaluators;
- deterministic runner behavior, including ordering, bounds, resume,
  idempotency, and execution-before-judgment binding;
- evaluation and dataset-generation context plus source-revision provenance;
- a Python API for application integration;
- a JSON-first `junjo eval` CLI suitable for humans, shell automation, and LLM
  coding agents; and
- a distributable skill and runbook that teach coding agents the same public
  contracts.

The CLI is an adapter over the Python API, not a second implementation.
Machine-readable JSON is the stable default for commands whose output is
consumed programmatically. Human-readable presentation may be additive.

MCP is a later thin adapter over the same SDK client and Studio API after those
semantics are proven. It does not define a parallel dataset, execution, or
query contract.

### Applications declare targets; they do not own the harness

Evaluation execution still occurs in the application process, from the source
checkout being evaluated. The application supplies a small typed declaration
for each supported target:

- stable application and target keys plus an input-contract version;
- the input type or schema;
- dependency and subject construction using real application code;
- the public Junjo execution entry point to invoke;
- the evaluator-facing subject projection; and
- domain-specific evaluator meaning that cannot be generalized truthfully.

The SDK accepts those declarations and owns dispatch, validation, lifecycle
coordination, result recording, and CLI behavior. Applications may provide
evaluator callbacks or composed domain evaluators, but do not reimplement the
evaluator framework, Studio client, DTOs, runner, retry policy, or command
orchestration.

### One executor lifetime owns application runtime resources

The SDK exposes one explicit asynchronous evaluation executor. Its lifetime is
the evaluation host lifetime, equivalent to an application server lifespan:
application-owned telemetry, provider clients, and other execution resources
are acquired lazily before the first real target execution, reused across
generated cases and evaluation Runs, and closed once when the executor exits.

Pure control operations, terminal Attempt inspection, interrupted bound-Attempt
recovery, and local Case contract failures do not acquire application runtime
resources. The installed CLI creates one executor for an execution command.
Programmatic callers may retain one executor across baseline and candidate
Runs. The SDK does not restart process-global OpenTelemetry state between
operations or hide it behind a process singleton.

Each Run is executed from one clean committed application source revision.
Studio stores that revision and a human Run label but does not select, inject,
or modify application prompts. Baseline and candidate are comparison roles
assigned to two Runs; they are not persisted entity types.

Studio never receives uploaded source or executable bundles and never
instantiates application dependencies. A coding agent edits and commits
ordinary application source, then invokes Junjo against the same locked
dataset and the application's target declarations.

### Studio is the evaluation control, evidence, and query plane

Studio owns canonical, bounded records for:

- immutable input datasets and ordered cases;
- labeled runs over one exact dataset;
- one pre-created attempt per run case;
- evaluator outcomes;
- exact semantic links between cases or attempts and Junjo executions; and
- bounded programmatic queries and comparisons over received evidence.

Studio is authoritative for evaluation status, reason, and membership.
Received telemetry remains authoritative for execution evidence. Studio does
not copy complete prompts, responses, state, conversations, spans, or traces
into evaluation-control records.

Evaluation judgments are binary. Every evaluator returns `passed` plus a
bounded reason. Studio stores `passed`, `failed`, or operational `error`;
there is no numeric score, mean score, or score delta.

Programmatic case authoring uses authenticated Studio APIs through the SDK.
The input dataset is the Studio Dataset plus its ordered Case records; this
decision does not introduce a file bundle or second dataset abstraction.

### Control records and telemetry use separate channels

Small dataset, run, attempt, binding, and result records use authenticated
Studio APIs. Complete execution evidence uses the existing OTLP trace path.

The control path never uploads trace payloads. The OTLP ingestion credential
never gains evaluation-control authority. Studio's ingestion service,
protobuf boundary, and shared telemetry contract do not change merely to
support these control records.

The SDK establishes authoritative evaluation context while preserving normal
application identity. The exact propagation and telemetry representation of
that context must be governed by its owning contract and validated across
Node, Workflow, Agent, and complete-flow execution. Application-domain
`ExecutionCorrelation` remains truthful and is not overloaded with dataset or
candidate identity.

Evaluation membership is bound to the exact semantic execution identity, not
inferred from a span name, service-name workaround, or replacement
application correlation.

### Execution binding precedes terminal judgment

Starting a run creates one attempt for every locked case. After application
execution yields a trustworthy runtime identity, the SDK runner binds that
identity to the attempt before invoking a potentially slow or fallible
evaluator. Binding and terminal result recording are separate idempotent
operations.

This preserves an exact evidence link when judging or result submission fails.
A resumed runner never executes an already-bound attempt again. If a bound
attempt has no terminal result after the previous process stopped, the runner
records an interrupted error; a new run is the explicit retry boundary.

There remains a small acknowledged crash window before the runtime identity is
durably bound. Solving that window would require a new trusted
telemetry-to-attempt reconciliation contract and is not hidden inside this
decision.

### Authentication is separately scoped

CLI and SDK evaluation control use a separately scoped evaluation-control
credential. Human users create and revoke those credentials through their
authenticated Studio browser session. Plain HTTP is accepted only for a
loopback Studio origin. The OTLP ingestion API key is never reused for this
purpose, and the SDK evaluation client does not accept Studio account
passwords.

### Generated-case retries avoid duplicate execution

Before generating a case, the SDK checks the current Dataset for its requested
case key. An existing generated case is returned without another provider call
only when its complete requested contract and clean source revision match.
Conflicting content fails before execution.

If execution succeeds but the first Case write never commits, that source trace
can remain unassociated and an explicit retry executes again. The MVP does not
add a pre-created generation lease or provisional Case state to close that
smaller window.

## Consequences

- Developers and coding agents receive one supported Junjo interface for
  authoring datasets, running application targets, recording results, and
  querying exact Studio evidence.
- Application repositories remain the truthful execution environment without
  becoming owners of generic evaluation mechanics.
- One explicit executor lifetime matches ordinary application resource
  ownership while allowing iterative baseline and candidate execution in one
  process.
- AI Chat becomes a reference declaration and end-to-end proof rather than a
  second evaluation framework.
- The Python SDK gains an intentional Studio-facing product surface in addition
  to execution and telemetry.
- Studio gains canonical product writes and bounded programmatic queries while
  complete trace evidence remains in its existing evidence plane.
- Target construction, dependency wiring, output projection, and domain
  evaluator meaning remain explicit application code.
- A process failure before durable execution binding can leave a visibly
  distinguishable but unassociated trace.

## Rejected alternatives

- Put the reusable client, DTOs, runner, and CLI in AI Chat: every application
  would copy Junjo policy, and coding agents would lack a stable product
  interface.
- Treat an application-owned harness as the long-term abstraction: execution
  is application-local, but orchestration and evaluation mechanics are Junjo
  responsibilities.
- Execute uploaded application code in Studio: Studio cannot safely or
  truthfully reconstruct application dependencies, credentials, or external
  state.
- Make Studio a remote execution scheduler: it would cross the source,
  dependency, and credential boundary without improving evidence ownership.
- Send traces through the evaluation API: this duplicates OTLP and the
  canonical Studio evidence path.
- Give ingestion API keys control-plane writes: transport admission is not
  application evaluation authority.
- Make MCP the primary implementation: MCP is useful agent ergonomics, but it
  must adapt stable SDK and API semantics rather than create another contract.
- Use trace IDs as evaluation identity: physical telemetry identity remains
  distinct from datasets, attempts, and Junjo runtime identity.
- Store result files or trace bundles as the primary contract: they are not a
  queryable shared control plane and duplicate evidence already received by
  Studio.

## Related decisions

- [ADR 0007: Application execution correlation and Studio resolution](0007-execution-correlation-and-studio-resolution.md)
- [ADR 0010: Node Evaluation Execution](0010-node-evaluation-execution.md)
- [ADR 0012: Studio integration is trace-only](0012-studio-trace-only-telemetry-integration.md)
- [ADR 0014: Bounded evaluation telemetry context](0014-evaluation-telemetry-context.md)
- [Studio ADR 010: Evaluation control persistence and API](../../apps/studio/docs/adr/010-evaluation-control-persistence-and-api.md)
- [Horizon 3 Evaluation Lean MVP](../roadmaps/AGENT_LAYER_HORIZON_3_LEAN_EVALUATION_MVP.md)
- [Horizon 3 Evaluation User Stories](../roadmaps/AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
- [Horizon 3 SDK Evaluation Productization Plan](../roadmaps/AGENT_LAYER_HORIZON_3_SDK_EVALUATION_PRODUCTIZATION_PLAN.md)
