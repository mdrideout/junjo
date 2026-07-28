# Horizon 3 Evaluation Product User Stories

- Status: Active product requirements
- Date: 2026-07-27
- Owners: Junjo platform
- Parent strategy:
  [Queryable Evaluation System And Iterative MVP Plan](AGENT_LAYER_HORIZON_3_QUERYABLE_EVALUATION.md)
- Implementation plan:
  [Horizon 3 Evaluation Lean MVP Critical Path](AGENT_LAYER_HORIZON_3_LEAN_EVALUATION_MVP.md)
- Engineering execution:
  [SDK Evaluation Productization Plan](AGENT_LAYER_HORIZON_3_SDK_EVALUATION_PRODUCTIZATION_PLAN.md)

## Document Role

This document captures the product outcomes Horizon 3 must deliver for
application developers and coding agents. It is the durable acceptance
reference for architecture, implementation plans, documentation, examples, and
skills.

These stories intentionally describe user-visible contracts rather than the
prototype's current file placement. Accepted ADRs own the final architecture,
but an implementation that satisfies a story by putting generic evaluation
mechanics in an example application does not satisfy this document.

Priorities mean:

- **P0 — product MVP:** required for the first supported, batteries-included
  evaluation loop;
- **P1 — next valuable slice:** expected after the P0 loop is proven and
  hardened; and
- **P2 — later extension:** useful, but it must reuse the P0 SDK and Studio
  contracts rather than create a parallel system.

## Product Promise

A developer installs Junjo in an application repository, declares how the
application's real Nodes, Workflows, and Agents are constructed, and then uses
Junjo's SDK or CLI to:

1. create or select a dataset in Junjo AI Studio;
2. execute that dataset against the checked-out application code;
3. send ordinary complete Junjo telemetry to Studio with exact evaluation
   identity;
4. record structured results against the exact dataset, candidate, case, and
   execution;
5. compare a baseline with later source or prompt candidates across the focal
   target and all observable downstream effects; and
6. query the same structured results and evidence from a coding agent.

The application repository remains the execution host because it owns the
source, dependencies, provider credentials, prompts, Tools, and domain
services. Junjo owns the evaluation framework used inside that host.

## Product Ownership Contract

| Owner | Responsibilities |
| --- | --- |
| Junjo Python SDK | Studio client and DTOs, the complete `EvaluationHarness`, target and evaluator abstractions, typed case validation flow, dataset/run/attempt coordination, resume and idempotency, evaluation telemetry context, exact execution binding, source provenance, result recording, evidence queries, comparisons, and the implementation behind the CLI |
| Application code | Explicit target declarations using SDK-owned types; typed domain inputs; callbacks that construct real application Nodes, Workflows, Agents, Stores, dependencies, and provider clients; output projections; and domain-specific evaluator meaning where Junjo's built-ins are insufficient |
| Junjo CLI | A stable, non-interactive, JSON-first interface over the same SDK services for developers, CI, coding agents, and future adapters |
| Junjo AI Studio | Authenticated dataset and evaluation control records, canonical trace evidence, execution membership, bounded semantic queries, result summaries, and comparison views |
| Coding-agent skill and runbooks | Teach an agent how to declare targets, create and lock datasets, execute candidates, inspect failures, compare evidence, and iterate safely; contain no hidden framework behavior |

An application may instantiate and configure an SDK `EvaluationHarness`, but it
must not implement its lifecycle. Application callbacks provide construction
and domain meaning; Junjo owns orchestration.

## Cross-Story Invariants

Every story below preserves these invariants:

- Studio never executes uploaded application source.
- The SDK never attempts to infer application construction from telemetry.
- The application never reimplements the Studio transport, control DTOs,
  attempt state machine, binding order, retry policy, or CLI.
- Dataset and result records reference canonical Studio evidence; they do not
  duplicate complete prompts, conversations, images, or trace payloads.
- Evaluation telemetry retains the application's truthful service identity and
  is distinguished with first-class evaluation context, not a fake service.
- The ingestion credential is not a Studio query or control-plane credential.
- The CLI, Python API, and any future MCP server share one service contract and
  one implementation of evaluation semantics.
- Node, Workflow, and Agent evaluation uses real public Junjo execution
  lifecycles. A target adapter must not call internal methods to simulate a
  successful execution.
- Defaults remain safe for a low-resource single-node Studio deployment:
  bounded pages, bounded concurrency, connection reuse, and no new query on the
  OTLP ingestion hot path.

## P0 Product MVP Stories

### H3-US-001 — Add Junjo Evaluation To An Application Repository

**As an application developer, I want to install and configure Junjo
Evaluation from the published Junjo distribution so that my application does
not need to copy framework code from an example.**

Outcome:

The repository has one small evaluation declaration module and ordinary
application-specific target construction. Studio transport, DTOs, runner
behavior, CLI commands, and retry logic come from the installed Junjo SDK.

Acceptance criteria:

- The published Python package exposes documented Studio client, evaluation,
  target, evaluator, and CLI APIs.
- A standalone repository can use those APIs without a monorepo workspace
  dependency or an import from AI Chat.
- Configuration distinguishes Studio control/query credentials from OTLP
  ingestion credentials.
- The SDK targets an explicit versioned Studio API and returns a structured
  incompatibility error instead of guessing, silently falling back, or
  continuing with an unsupported response contract.
- A minimal setup guide and application-local coding-agent runbook explain the
  same supported path.
- The AI Chat example consumes the published interfaces and contains no generic
  Studio client, DTO, runner, resume, or result-write implementation.

Not part of this story:

- generating application targets by inspecting arbitrary source;
- copying the AI Chat framework implementation into another repository; or
- installing Studio runtime code as an SDK dependency.

### H3-US-002 — Declare Typed Node, Workflow, And Agent Targets

**As an application developer, I want to register my real Junjo execution
targets with an SDK-owned harness so that one framework can run typed cases
against Nodes, Workflows, and Agents.**

Outcome:

The application supplies domain construction callbacks and types. The Junjo
SDK selects the target, validates the case, invokes the correct public
lifecycle, captures identity, and returns a uniform evaluation execution
result.

Acceptance criteria:

- The SDK owns explicit `Node`, `Workflow`, and `Agent` evaluation target
  abstractions with stable target keys and versioned input contracts.
- An application declaration can supply a typed input model, construction
  callback, required dependency/provider context, and output projection.
- The Node abstraction uses Junjo's truthful Node evaluation lifecycle; the
  Workflow and Agent abstractions use their real public execution lifecycles.
- The harness rejects an unknown target key, wrong target kind, or invalid
  input before it records a successful subject binding.
- The harness returns the semantic execution identity needed by Studio without
  requiring application code to construct Studio DTOs.
- The same application declaration can include focused Node targets and wider
  Workflow or Agent targets.
- Target registration is explicit and inspectable; a coding agent can list
  target keys and input schemas through the CLI.

Not part of this story:

- automatically discovering every callable or Junjo object in a repository;
- serializing arbitrary dependency containers into Studio; or
- making the SDK understand application-domain constructor semantics.

### H3-US-003 — Create And Lock An Authored Input Dataset

**As an application developer or coding agent, I want to create cases
programmatically and lock an exact ordered dataset so that every candidate runs
against the same inputs.**

Outcome:

Studio owns an immutable comparison unit while the Junjo SDK and CLI provide
the supported authoring workflow.

Acceptance criteria:

- The Python client and CLI can create, get, list, add cases to, and lock a
  dataset through authenticated Studio APIs.
- A case identifies its target kind and key, input contract version, typed
  input, expectation, evaluator key and version, and stable case key.
- The SDK validates the case input against the declared application target
  before requesting dataset lock.
- Lock freezes the exact ordered case records and prevents later mutation.
- Repeating a create or add operation with the same canonical natural identity
  and payload returns the existing result; conflicting reuse fails explicitly.
- CLI output includes stable dataset and case IDs that an agent can pass to
  later commands without parsing prose.

Not part of this story:

- a spreadsheet or file-upload trace-import workflow;
- mutable changes to a dataset after it has been used for comparison; or
- treating one prior model response as ground truth automatically.

### H3-US-004 — Generate Dataset Material Through Real Application Execution

**As an application developer or coding agent, I want to run a declared target
in dataset-generation mode so that I can collect truthful input, output, and
complete flow evidence before curating a case.**

Outcome:

Dataset generation uses the same SDK harness and real application lifecycle as
candidate evaluation. Studio can identify the generation execution and retain
its complete received evidence membership.

Acceptance criteria:

- The SDK can execute a declared Node, Workflow, or Agent target with evaluation
  class `dataset_generation`.
- The generated material retains the submitted input, selected output
  projection, exact execution reference, clean source revision, target key,
  and evidence-readiness state.
- A Workflow or Agent generation execution preserves all received nested and
  downstream telemetry, even when only one focal output becomes a case member.
- The user can explicitly promote selected generated material into a draft
  dataset case.
- Retry after an uncertain add response does not execute the provider-backed
  target twice when the same generated case was already accepted.
- Locking a generated case applies an explicit complete, partial, or unknown
  evidence policy; missing telemetry is never silently called complete.

Not part of this story:

- automatically declaring generated output to be the expected correct answer;
- materializing every descendant span as a separate dataset case; or
- reconstructing an application execution from stored telemetry alone.

### H3-US-005 — Run One Dataset Against A Baseline Or Candidate

**As a coding agent, I want Junjo to execute a locked dataset against the code
in my checkout so that I can measure a prompt or implementation candidate
without writing orchestration logic.**

Outcome:

One SDK-owned harness command owns the complete Dataset → Run → Attempt →
Execution → Result lifecycle while application callbacks only construct and
interpret the target.

Acceptance criteria:

- The harness receives a locked dataset and explicit candidate label and
  executes every case against the declared target.
- A run records the clean source revision and refuses an uncommitted candidate
  by default, with any deliberate override visible in provenance.
- The SDK pre-creates or claims attempts, executes each subject, binds its exact
  semantic execution reference before judging, and records a typed terminal
  result.
- A single dataset may contain Node, Workflow, and Agent cases when all target
  declarations are available.
- `EvaluationExecutor` is sequential and bounded and owns one explicit
  application-host runtime lifetime.
- The result identifies dataset, run, case, attempt, candidate, evaluator,
  duration, pass/fail/error state, score where applicable, and a bounded reason.
- The CLI can run the same declaration as the Python API without application-
  local control-plane code.

Not part of this story:

- Studio checking out or executing the candidate source;
- a distributed scheduler or general-purpose job queue; or
- claiming deterministic comparison when provider or environment inputs are
  uncontrolled.

### H3-US-006 — Evaluate With SDK-Owned Contracts And Open Domain Meaning

**As an application developer, I want Junjo to own evaluator execution and
result contracts while allowing my application to supply domain-specific
meaning so that evaluations are consistent without becoming closed or
application-blind.**

Outcome:

The SDK provides evaluator interfaces, built-in deterministic evaluators,
common result schemas, timeouts, error handling, and identity. Applications
only implement genuinely domain-specific checks or judge prompts.

Acceptance criteria:

- The SDK owns evaluator registration, dispatch, timeout, exception
  normalization, result validation, and result recording.
- Built-in evaluators cover exact equality, structured field checks, and other
  deterministic primitives justified by the MVP.
- An application evaluator receives a typed target output projection and typed
  expectation through an SDK-owned interface.
- Every evaluator has a stable key, version, configuration fingerprint, and
  structured result schema.
- Subject, judge, and verifier failures remain distinguishable.
- An evaluator cannot silently replace a bound subject execution or copy the
  subject output into its own expected answer.

Not part of this story:

- a Studio-hosted arbitrary evaluator-code runtime;
- requiring an LLM judge for every case; or
- hiding evaluator prompts and versions from comparison provenance.

### H3-US-007 — Correlate Evaluation Results With Complete Telemetry

**As an application developer, I want an evaluation attempt to be visibly
distinct from production traffic while retaining my application's real service
identity so that Studio can query the result and the entire execution tree
together.**

Outcome:

The SDK establishes first-class evaluation context around real execution.
Ordinary Junjo telemetry reaches Studio through OTLP and the evaluation ledger
binds to its exact semantic identity.

Acceptance criteria:

- The SDK creates a lightweight evaluation-attempt context containing at least
  dataset ID, run ID, case ID, attempt ID, evaluation class, and execution role.
- That context propagates through the supported subject execution without an
  application callback manually adding attributes to each span.
- The target continues to use the application's truthful service namespace and
  service name.
- Studio can distinguish application, dataset-generation, evaluation-subject,
  judge, and verifier evidence where those roles exist.
- The attempt is bound to the exact execution identity before a result is
  written.
- The normal OTLP path remains the only trace payload path; evaluation REST
  requests contain bounded control and result metadata.
- The implementation adds no synchronous Studio query or SQLite lookup to the
  ingestion hot path.

Not part of this story:

- creating a fake `*-evals` application service solely for classification;
- copying the complete trace into evaluation tables; or
- assuming exporter flush proves complete persistence.

### H3-US-008 — Query Results And Exact Evidence Programmatically

**As a coding agent, I want structured access to runs, attempts, execution
membership, and trace evidence so that I can diagnose failures without scraping
the Studio UI.**

Outcome:

The agent can move from a dataset or run to an exact failing subject and its
received evidence using bounded SDK or CLI queries.

Acceptance criteria:

- The client and CLI can list and get datasets, runs, cases, attempts, and
  terminal results with bounded pagination.
- An attempt query returns its exact semantic execution reference and evidence
  readiness or integrity status.
- Evidence queries can return the complete received trace plus Studio's
  normalized Workflow, Agent, Node, Tool, model-operation, Store, relationship,
  and loss annotations where present.
- Exact IDs and machine-readable next-page tokens are returned without relying
  on timestamps as identity.
- The agent can request concise summaries first and explicitly hydrate larger
  evidence, avoiding a fanout query for every row.
- Studio UI deep links and programmatic query results resolve the same
  execution.

Not part of this story:

- exposing raw SQLite, SQL, Parquet paths, or DataFusion plans;
- inventing evidence that Studio did not receive; or
- requiring a browser session to inspect structured results.

### H3-US-009 — Compare Baseline And Candidate Across The Whole Flow

**As an application developer or coding agent, I want to compare the same cases
across two runs and follow an upstream change through downstream telemetry so
that I can detect progression, regression, and unintended effects.**

Outcome:

Studio pairs attempts by immutable case identity and exposes both evaluation
results and the complete evidence scopes needed to understand a change.

Acceptance criteria:

- A comparison names one baseline run and one candidate run over the same
  locked dataset.
- Cases pair by stable case identity, not list position, label, or timestamp.
- The comparison reports result status and score changes, missing or extra
  attempts, source revisions, target/evaluator versions, and evidence
  integrity.
- For a focused upstream Node or model behavior inside a Workflow or Agent, the
  user can reach both focal evidence and the declared wider comparison scope.
- The user can inspect prompts, model requests and responses, Tool calls, state
  transitions, outputs, and downstream spans that Studio actually received.
- Programmatic comparison is available through the same SDK contract used by
  the Studio UI.

Not part of this story:

- claiming semantic causal attribution solely from temporal ordering;
- requiring a perfect automatic span-alignment algorithm for MVP; or
- automatically promoting a candidate because its aggregate score increased.

### H3-US-010 — Resume Safely After Interruption Or Partial Failure

**As a coding agent, I want an interrupted run to resume without duplicating
provider calls or overwriting evidence so that long or costly evaluations are
safe to operate.**

Outcome:

The SDK owns an explicit attempt state machine and idempotent recovery rules.
The agent can distinguish retryable control failure, subject failure, judge
failure, and missing evidence.

Acceptance criteria:

- Re-running with the same run identity discovers completed, bound, running,
  and retryable attempts.
- A completed attempt is never executed again by resume.
- A bound subject is never executed again merely because result or judge
  recording was interrupted.
- Conflicting execution bindings or terminal results fail closed and preserve
  the first accepted record.
- Retryable Studio transport errors use bounded backoff while preserving the
  same canonical natural identity and payload.
- The CLI reports resumable and non-resumable cases in structured output and
  uses stable exit status categories.
- A cancelled local process leaves enough Studio state for deterministic
  recovery.

Not part of this story:

- exactly-once behavior from an external model provider that offers no such
  contract;
- silently retrying a non-idempotent application side effect; or
- hiding partial evidence behind a passing evaluation result.

### H3-US-011 — Operate Junjo Reliably From A Coding Agent

**As a coding agent, I want a discoverable, non-interactive, JSON-first Junjo
CLI so that I can operate evaluations without guessing commands or parsing
human prose.**

Outcome:

The CLI is a thin adapter over the public Python client and harness. It is a
stable automation surface for local agents and CI, with human-readable output
available as a presentation option.

Acceptance criteria:

- `junjo eval` provides target discovery, dataset authoring and locking, run
  execution and resume, run comparison, and attempt evidence commands.
- Every command supports a documented structured output envelope with schema
  version, success data or typed error, stable resource IDs, and bounded
  pagination.
- Commands have stable exit status categories and never require an interactive
  prompt when non-interactive mode is selected.
- Inputs can be supplied through files or standard input where payloads are
  non-trivial; secrets are not accepted in a form that is routinely exposed in
  process listings or output.
- A capability command reports CLI, SDK, Studio API, and evaluation contract
  versions.
- `--help` includes complete examples and the SDK publishes the corresponding
  request and response schemas.
- Logs and progress go to standard error when structured results go to standard
  output.
- The coding-agent skill invokes these supported commands and does not
  reimplement API calls with ad hoc shell scripts.

Not part of this story:

- an independent CLI state machine separate from the Python SDK;
- an LLM-specific wire format that humans and ordinary automation cannot use;
  or
- making MCP a prerequisite for the first useful loop.

### H3-US-012 — Authenticate Automation Without Expanding Ingestion Authority

**As an application developer, I want a scoped Studio credential for Junjo
evaluation automation so that my coding agent can manage datasets and query
evidence without reusing telemetry ingestion authority.**

Outcome:

Control/query access and telemetry ingestion remain separate security
boundaries. Credentials can be revoked, scoped, and redacted independently.

Acceptance criteria:

- Studio provides an authenticated non-browser mechanism suitable for CLI and
  unattended automation.
- The credential can be scoped to the minimum evaluation read/write and
  evidence-read permissions supported by the MVP.
- The Junjo client loads credentials from documented environment or protected
  configuration sources and redacts them from logs and structured errors.
- Remote control/query traffic requires TLS; any plain HTTP development
  allowance is loopback-only and explicit.
- Revoking an evaluation credential does not require rotating the application's
  OTLP ingestion key, and the ingestion key cannot mutate datasets.
- Authentication failures are distinct from compatibility, validation, and
  transient availability failures.

Not part of this story:

- turning an OTLP API key into a general Studio control token;
- storing a user's browser password in application Compose configuration; or
- granting a coding agent Studio administration privileges by default.

### H3-US-013 — Remain Useful On A Low-Resource Studio Deployment

**As a self-hosted developer, I want evaluation operations to preserve Studio's
low-resource behavior so that I can iterate locally or on a small VM.**

Outcome:

The control plane remains small, the evidence plane remains hot/cold and
query-on-demand, and application execution consumes resources only when the
user invokes it.

Acceptance criteria:

- The SDK client reuses long-lived HTTP connections and applies bounded
  request, retry, and response limits.
- The runner defaults to sequential execution and exposes a small explicit
  concurrency bound rather than scaling with dataset size.
- List and comparison endpoints are indexed, paginated, and do not hydrate full
  trace payloads by default.
- Evidence retrieval is explicit and bounded; large payloads can be streamed or
  paged without retaining an entire dataset's traces in process memory.
- Evaluation control records remain in Studio's canonical control database and
  complete telemetry remains in the existing evidence architecture.
- Live validation records idle and active RSS, CPU, latency, case throughput,
  ingestion volume, evidence resolution, and database contention for a
  representative small-profile loop.
- A regression budget is defined from measured baseline behavior before
  concurrency or automatic hydration is increased.

Not part of this story:

- a new always-running evaluation worker, queue, or cache service;
- loading all baseline and candidate traces into the frontend at once; or
- optimizing hypothetical large-scale scheduling before measuring the single-
  node loop.

### H3-US-014 — Use Deterministic Evaluation In CI

**As an application developer, I want selected locked datasets to run in CI so
that important behavior regressions can block a change with inspectable
evidence.**

Outcome:

CI invokes the same Junjo CLI and application target declarations used locally,
then publishes stable machine-readable results and Studio evidence links.

Acceptance criteria:

- CI can run an explicitly selected locked dataset non-interactively at the
  checked-out commit.
- The command supports a documented policy for which failed, errored, partial,
  or missing-evidence outcomes produce a failing exit status.
- Deterministic evaluators can be required gates; probabilistic or costly
  provider-backed suites are opt-in and visibly classified.
- Run metadata records the source revision and CI correlation without treating
  a branch label as immutable identity.
- Re-running a CI job can resume the same run only when explicitly requested;
  a new candidate run is otherwise distinct.
- CI output contains a concise summary plus exact Studio links and structured
  artifacts suitable for later automation.

Not part of this story:

- making every live-model evaluation a merge gate;
- masking infrastructure failure as application regression; or
- granting pull-request code unrestricted long-lived Studio credentials.

## P1 Next Valuable Stories

### H3-US-101 — Curate A Dataset From Historical Studio Evidence

**As a coding agent, I want to select prior application runs or executable
evidence as dataset inputs so that production and exploratory behavior can
become a repeatable regression corpus.**

Outcome:

The agent queries bounded semantic evidence, selects exact anchors, projects
approved input material, and creates draft cases that retain provenance.

Acceptance criteria:

- The SDK can search supported historical executions by bounded facets such as
  service, run or trace ID, executable runtime ID, target kind/key, time,
  outcome, and correlation.
- Selection resolves to exact trace/span anchors before a case is created.
- A case records its historical source reference, projection key/version, and
  evidence integrity.
- The target input contract validates the projected input before dataset lock.
- The developer can redact, transform, or reject sensitive historical material
  through an explicit application policy.
- The original evidence remains canonical and queryable; the case stores only
  the bounded input/expectation material required for rerun plus provenance.

Not part of this story:

- assuming every historical trace contains sufficient input to rerun;
- bulk-importing all production traffic without curation; or
- replaying external-world state, side effects, credentials, or time merely
  because a trace recorded them.

### H3-US-102 — Build Focused And End-To-End Cases From One Generated Flow

**As an application developer, I want one deliberate Workflow or Agent
generation run to support both end-to-end and focused dataset cases so that I
can test individual decision points without losing their wider context.**

Outcome:

Studio retains one canonical generated execution while dataset cases can name
different focal entities, inputs, projections, and comparison scope roots.

Acceptance criteria:

- The generated evidence set has one exact subject root and a queryable
  membership rule for nested executable and operation evidence.
- A user can create an end-to-end case from the root and focused Node, Agent,
  model-operation, or Tool cases from supported members.
- Every focused case retains a link to the source flow and its wider comparison
  scope.
- Multiple cases reference canonical evidence without duplicating the trace.
- Case creation makes required input availability and projection limits
  explicit.

Not part of this story:

- automatically converting every span into a useful case;
- pretending a downstream observation is an independently executable target;
  or
- requiring complete automatic causal inference.

### H3-US-103 — Query Evaluation Cohorts And Regressions

**As a coding agent, I want bounded semantic queries across evaluation runs so
that I can identify recurring failures and choose the next change based on
evidence.**

Outcome:

Studio exposes stable cohort and aggregate queries without exposing its storage
implementation.

Acceptance criteria:

- Queries can filter by dataset, case, target, candidate, source revision,
  evaluator, result status, score range, execution outcome, and evidence
  integrity.
- Aggregate responses are bounded and link back to exact attempts and traces.
- Saved query semantics are versioned and shared by SDK, CLI, UI, and future
  MCP adapters.
- An agent can request failed-case summaries before hydrating exact evidence.
- Query results identify missing or partial data and never silently exclude it
  from denominators.

Not part of this story:

- public raw SQL or storage-engine query plans;
- an unbounded analytics endpoint; or
- vector search without a measured semantic retrieval need.

### H3-US-104 — Extend Targets And Evaluators Without Forking Junjo

**As a library or application developer, I want documented extension contracts
so that new target construction and domain evaluators compose with the same
Junjo harness.**

Outcome:

Extensions provide domain behavior at explicit interfaces while Junjo retains
ownership of orchestration, telemetry context, identity, and result contracts.

Acceptance criteria:

- Public protocols define target input validation, construction, invocation,
  output projection, evaluator input, and evaluator result boundaries.
- Extension keys and versions are explicit; registration has no import-time
  global side effects.
- The harness can list extension metadata and schemas without executing a
  provider call.
- Extensions cannot bypass attempt binding or write arbitrary terminal states.
- Contract tests are available to application authors.
- A second reference application proves the interfaces are not accidentally
  AI Chat-specific before extraction grows beyond demonstrated needs.

Not part of this story:

- plugin discovery that executes arbitrary installed packages implicitly;
- application control over the evaluation state machine; or
- SDK abstractions for one-off domain conveniences.

### H3-US-105 — Run A Human Review Stage

**As an application developer, I want selected attempts to receive structured
human review so that subjective cases can complement automated evaluators
without losing provenance.**

Outcome:

Human review is one versioned result role associated with the same attempt and
evidence, not an overwrite of automated evaluation.

Acceptance criteria:

- Review assignments reference exact attempts and evidence.
- Reviewer identity, rubric version, decision, score, reason, and timestamp are
  retained.
- Automated, model-judge, external-verifier, and human results remain
  distinguishable.
- Comparison can select or display the relevant result roles explicitly.

Not part of this story:

- requiring human review for the P0 loop; or
- silently treating human opinion as deterministic ground truth.

## P2 Later Extension Stories

### H3-US-201 — Expose The Same Contract Through MCP

**As a coding agent with MCP support, I want Junjo evaluation tools exposed
through MCP so that I can use typed tool calls instead of shell commands.**

Outcome:

MCP is a thin, permission-aware adapter over the same public Junjo client,
schemas, and error semantics.

Acceptance criteria:

- MCP tools map directly to supported SDK operations and use the same
  authentication scopes.
- Resource IDs, pagination, idempotency, compatibility, and structured errors
  match CLI and Python behavior.
- Large evidence is exposed through bounded resources or pagination rather
  than oversized tool results.
- CLI remains supported for repositories and agents without MCP.

Not part of this story:

- a second evaluation service implementation;
- MCP-only dataset or result semantics; or
- giving an MCP server broader Studio authority than the calling user.

### H3-US-202 — Support Other Language SDK Harnesses

**As an application developer using another Junjo SDK, I want equivalent
evaluation contracts so that datasets and Studio comparisons are language
independent.**

Outcome:

Language SDKs implement shared semantics and conformance fixtures while using
idiomatic target and type systems.

Acceptance criteria:

- Dataset, run, attempt, evaluation-context, result, and evidence-query
  semantics have language-independent schemas and fixtures.
- Each language owns an idiomatic client and harness implementation.
- A dataset can compare candidates implemented in different supported
  languages when target and evaluator contracts are compatible.
- No language SDK imports another language's runtime implementation.

Not part of this story:

- forcing mechanical source-code abstractions across languages; or
- delaying a correct Python MVP until every language has parity.

### H3-US-203 — Coordinate Larger Evaluation Runs

**As a team with a measured larger workload, I want bounded parallel or
distributed execution so that evaluation time can improve without weakening
attempt ownership or low-resource defaults.**

Outcome:

Scheduling grows only after measurements demonstrate the need. Attempt leasing,
heartbeats, cancellation, and concurrency remain Junjo-owned contracts.

Acceptance criteria:

- The existing sequential runner remains the default.
- Parallel execution has explicit concurrency, memory, provider-rate, and
  application-safety bounds.
- Attempt leases prevent duplicate workers from claiming the same subject.
- Cancellation and worker loss leave resumable states.
- Capacity tests quantify throughput and resource impact before defaults
  change.

Not part of this story:

- embedding a general distributed compute platform in Studio; or
- increasing default concurrency based on dataset size alone.

### H3-US-204 — Assist An Iterative Improvement Loop

**As a coding agent, I want to use query and comparison evidence to propose and
measure the next source change so that Junjo supports disciplined iterative
improvement.**

Outcome:

The agent can select a regression cohort, edit ordinary application source,
run the same locked dataset, compare evidence, and report why a candidate did
or did not improve.

Acceptance criteria:

- Every iteration identifies its parent or baseline run and immutable source
  revision.
- The agent can query exact failing evidence and downstream effects before
  proposing a change.
- Promotion remains an explicit repository and deployment decision.
- Studio retains unsuccessful candidates and their evidence instead of showing
  only the winner.
- Loop limits, model/provider cost, and stop conditions are explicit.

Not part of this story:

- autonomous production deployment;
- self-modifying prompts stored only in Studio rather than application source;
  or
- optimizing one score while hiding regressions, missing cases, or partial
  evidence.

## Reference End-To-End User Journey

The following journey is the acceptance narrative for the supported product.
It should work in AI Chat and in a standalone application repository using the
published Junjo package.

1. The developer declares typed Node, Workflow, and Agent targets with
   SDK-owned target abstractions. The declarations contain only application
   construction, dependencies, output projection, and domain evaluator
   bindings.
2. A coding agent runs target discovery and receives stable target keys and
   input schemas as structured output.
3. The agent creates a draft dataset in Studio through the Junjo CLI, adds
   authored inputs, and optionally executes a real generation target to curate
   additional cases.
4. Junjo validates the cases against the application declarations and locks
   the ordered dataset.
5. The agent checks out or commits a clean baseline revision and asks the
   SDK-owned harness to run the locked dataset.
6. The harness creates the run and attempts, executes the real application
   targets, applies evaluation telemetry context, binds each exact execution,
   runs registered evaluators, flushes telemetry, and records results.
7. The agent queries the run and exact evidence through structured Junjo
   commands. Studio shows the same data and deep links.
8. The agent changes an upstream prompt or implementation in ordinary
   application source, commits a candidate, and runs the same locked dataset.
9. The agent compares paired cases, focal operations, complete Workflow or
   Agent scopes, and all received downstream evidence.
10. The agent reports progression, regression, uncertainty, missing evidence,
    and the next recommended source change. The developer retains normal
    authority over promotion.

## Product-Level Definition Of Done

The P0 product is complete only when:

- all P0 stories pass in a standalone application checkout using the published
  Junjo package;
- AI Chat contains application declarations and domain behavior but no generic
  evaluation framework or Studio client implementation;
- Python API, CLI, Studio UI, and coding-agent runbook agree on the same
  identities, state transitions, and errors;
- Node, Workflow, and Agent targets each have a real end-to-end proof;
- authored and generated cases can be locked and rerun;
- baseline and candidate comparisons link results to exact complete evidence;
- interruption and resume are validated without duplicate bound subject
  execution;
- authentication uses separate least-authority control/query and ingestion
  credentials;
- low-resource measurements demonstrate no material ingestion-path regression
  or unbounded evaluation query behavior; and
- SDK, Studio, contracts, docs, example, and live E2E validation all pass for
  every changed boundary.

Historical evidence curation is P1 because it requires a broader semantic
selection and projection contract. The P0 design must not block it: every
generated and evaluated execution already retains exact anchors, provenance,
and queryable evidence membership.
