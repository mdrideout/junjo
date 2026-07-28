# Horizon 3 SDK Evaluation Productization Plan

- Status: Implemented and validated
- Date: 2026-07-27
- Owners: Junjo Python SDK, Junjo AI Studio, and AI Chat
- Product requirements:
  [Horizon 3 Evaluation User Stories](AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
- Lean scope and exit gates:
  [Horizon 3 Evaluation Lean MVP](AGENT_LAYER_HORIZON_3_LEAN_EVALUATION_MVP.md)
- North-star strategy:
  [Horizon 3 Queryable Evaluation System](AGENT_LAYER_HORIZON_3_QUERYABLE_EVALUATION.md)
- Owning architecture:
  [ADR 0013: SDK-orchestrated, application-executed Studio evaluations](../adr/0013-application-executed-studio-evaluations.md)
- Studio persistence and API:
  [Studio ADR 010: Evaluation control persistence and API](../../apps/studio/docs/adr/010-evaluation-control-persistence-and-api.md)
- Evaluation telemetry:
  [ADR 0014: Bounded evaluation telemetry context](../adr/0014-evaluation-telemetry-context.md)

## Document Role

This document is the engineering execution plan for turning the validated
AI Chat evaluation walking skeleton into a supported Junjo SDK product. It owns
implementation order, component boundaries, migration steps, and completion
gates.

It does not redefine product behavior or architecture. The user stories own
product acceptance, the Lean MVP owns scope, and the accepted ADRs own system
boundaries. When this plan and an owning ADR disagree, the ADR wins and this
plan must be corrected before implementation continues.

## Accepted Outcome

An application developer installs Junjo, declares typed Node, Workflow, and
Agent targets, and uses the Junjo Python API or `junjo eval` CLI to create and
lock Studio datasets, run those datasets against application code, record
results, and query the exact telemetry Studio received.

The Junjo SDK owns:

- the Studio client, DTOs, authentication integration, and typed errors;
- the complete `EvaluationHarness`;
- target and evaluator abstractions;
- dataset, run, attempt, and result coordination;
- deterministic ordering, bounds, resume, and idempotency;
- execution binding before judgment;
- evaluation and dataset-generation telemetry context;
- source-revision provenance;
- evidence and comparison queries;
- the JSON-first CLI; and
- public documentation and the coding-agent skill.

Application code owns only:

- stable target keys and versioned typed inputs;
- construction of real application dependencies, Stores, Nodes, Workflows,
  Agents, and provider clients;
- output projection;
- fixtures and domain data; and
- evaluator callbacks where Junjo's built-ins cannot express the domain
  judgment truthfully.

Studio owns canonical datasets, cases, runs, attempts, results, execution
membership, bounded evidence queries, and human result views. Complete trace
payloads continue to enter Studio through ordinary authenticated OTLP.

## Non-Negotiable Constraints

- AI Chat must not remain the owner of any generic evaluation framework code.
- Studio never receives or executes uploaded application source.
- The control API never becomes a second telemetry-upload path.
- The OTLP ingestion key never becomes a Studio control/query credential.
- Evaluation execution retains the application's normal OpenTelemetry service
  identity.
- Evaluation metadata is not copied onto every descendant span.
- The Rust ingestion hot path gains no synchronous query, new database lookup,
  cache, service, or protocol.
- `EvaluationExecutor` is sequential and bounded.
- The CLI, Python API, and later MCP adapter share one implementation of
  evaluation semantics.
- No compatibility fallback keeps the AI Chat-local framework alive after the
  SDK cutover.

## Starting Point

The walking skeleton has already validated:

- Studio Dataset, Case, Run, and Attempt persistence;
- bounded authenticated REST routes;
- idempotent Dataset, Case, Run, execution-binding, and result writes;
- exact semantic execution membership;
- read-only Studio run, detail, and comparison views;
- AI Chat Node and Workflow execution;
- authored and generated cases;
- interruption and resume behavior;
- exact trace-evidence links; and
- acceptable small-profile resource behavior.

The architectural defect is ownership. The reusable client, DTOs, runner,
command, and target/evaluator mechanics currently live under AI Chat. This plan
productizes those mechanics in the Junjo SDK and leaves only application
bindings in AI Chat.

## Target SDK Shape

The intended public ownership is:

| SDK area | Responsibility |
| --- | --- |
| `junjo.studio` | Typed Studio client, DTOs, authentication configuration, errors, pagination, evidence, and comparison operations |
| `junjo.evaluation` | Harness, immutable context, target declarations, evaluators, result contracts, runner, provenance, and resume/idempotency behavior |
| `junjo.cli` | `junjo eval` parsing and presentation over the public SDK APIs |
| Existing `junjo.eval` | Narrow faithful `evaluate_node()` primitive retained under ADR 0010 |

Suggested internal files may include:

- `junjo/studio/models.py`, `client.py`, and `errors.py`;
- `junjo/evaluation/context.py`, `targets.py`, `evaluators.py`, `runner.py`,
  `harness.py`, and `provenance.py`; and
- `junjo/cli/main.py` and `junjo/cli/eval.py`.

The final file split may remain smaller where responsibilities are still
cohesive. Public objects must be exported deliberately through the owning
package, documented, and included in the Griffe public-surface contract.

The SDK may use the async HTTP client already proven by the walking skeleton.
One client instance is reused for the command or harness lifetime so requests
share connection pooling, cookie or token configuration, timeouts, and bounded
response behavior. There is no process-wide daemon or default response cache.

## Target And Evaluator Contract

`EvaluationHarness` accepts one explicit application key plus registered
SDK-owned target and evaluator declarations.

Every target declaration supplies:

- target kind and stable key;
- positive input-contract version;
- a typed input model or equivalent JSON schema;
- an application callback that constructs fresh dependencies and the real
  executable subject;
- any invocation input required by the public lifecycle; and
- an output projector returning the evaluator subject.

SDK target types own the known Junjo lifecycle:

- `NodeTarget` constructs a fresh Node and Store, then uses
  `evaluate_node()`;
- `WorkflowTarget` constructs a fresh Workflow and invokes its public
  execution lifecycle; and
- `AgentTarget` constructs a fresh Agent and invokes its public execution
  lifecycle.

The application callback does not perform Studio writes or recreate the runner.
Unknown keys, kinds, input versions, or invalid inputs fail before provider
work.

The SDK evaluator framework owns registration, dispatch, timeouts, exception
normalization, result validation, and result recording. Initial built-ins
should remain small:

- exact equality;
- typed or structured-field checks; and
- boolean predicate evaluation.

AI Chat may register a domain-specific local-place quality evaluator callback.
That callback returns the SDK-owned result type and does not control Attempt
state transitions or Studio writes.

## Studio Client Contract

The existing versioned Studio API and OpenAPI document are the server contract.
The Python SDK owns idiomatic strict Pydantic DTOs and typed errors; it does not
import Studio runtime code.

Contract validation must prove that SDK requests and responses remain
compatible with Studio OpenAPI. The client fails explicitly on unsupported
response contracts and never adds silent fallback fields or alternate routes.

The client owns:

- one bounded connection pool per client lifetime;
- explicit connect/read/write timeouts;
- bounded pagination;
- retries that preserve the same canonical natural identity and payload;
- typed authentication, validation, conflict, pending-evidence, ambiguous
  identity, transient-availability, and contract errors;
- secret redaction; and
- explicit close and async-context-manager behavior.

Control operations return summaries by default. Complete trace evidence is
hydrated only through an explicit request.

## CLI Contract

The Python API is canonical. The CLI is a thin, tested adapter installed as a
standard Python project script.

Use standard-library `argparse` for the initial CLI. Pydantic remains the
source of payload validation and JSON schemas. This avoids a second command
framework dependency while preserving a typed product contract.

The initial command groups are:

- `junjo eval targets list`;
- `junjo eval dataset create|list|get|add|lock`;
- `junjo eval case generate`;
- `junjo eval run execute|resume|list|get|compare`;
- `junjo eval attempt get|evidence`; and
- `junjo eval execution membership`.

Execution commands load exactly one explicit `module:object`
`EvaluationHarness`. The harness location may come from a command option or
one application-owned `pyproject.toml` setting. There is no implicit import
scan, entry-point discovery, or global registry.

Machine output uses a versioned JSON envelope with either data or one typed
error. Structured data goes to standard output. Progress and diagnostics go to
standard error. Exit statuses distinguish at least usage/validation,
authentication, conflict, subject execution, evaluator failure, pending
evidence, and transient Studio availability.

Non-trivial JSON input may come from a file or standard input. Secrets are
never accepted through routinely visible command arguments and never appear in
structured output.

## Programmatic Authentication

Coding-agent and CI operation uses a separately scoped Studio control/query
token. Human browser sessions only create, list, and revoke those tokens; the
SDK has no email/password authentication API.

The smallest supported token model has:

- a user-visible name and non-secret prefix;
- a high-entropy secret shown once;
- one-way secret storage;
- explicit evaluation-read, evaluation-write, and evidence-read scopes;
- optional expiration;
- explicit revocation; and
- no per-request last-used database write.

Studio authenticates this token in the backend control plane. It is not sent to
ingestion and does not authorize OTLP. The existing ingestion API key is not
accepted by evaluation routes.

The Studio UI needs one minimal token create/list/revoke surface that clearly
distinguishes these tokens from ingestion API keys. The CLI reads the token
from protected environment or configuration, initially
`JUNJO_AI_STUDIO_CLI_TOKEN`. Remote Studio origins require HTTPS; loopback
development may use explicit HTTP.

OAuth or device authorization is deferred until hosted or multi-tenant use
demonstrates the need. A later remote MCP adapter must follow its own accepted
authorization contract rather than widening the MVP token silently.

## Evaluation Telemetry Context

The SDK creates one bounded evaluation-attempt orchestration root around each
real subject execution. It propagates an immutable `EvaluationContext` through
subject, judge, and verifier work.

The minimum context identifies:

- run class: application, dataset generation, or evaluation;
- dataset ID;
- run ID;
- case ID;
- attempt ID;
- source revision; and
- execution role: orchestrator, subject, judge, or verifier.

ADR 0014 owns the finalized attribute names, bounded role-span topology, and
contract-version decision. Junjo-specific identity uses the stable
`junjo.evaluation.*` namespace. A compatible OpenTelemetry GenAI evaluation
convention may replace equivalent Junjo-specific fields only through a later
explicit contract decision.

The application retains its real service namespace and service name. The
context appears on the bounded orchestration and role boundaries, not on every
span. Node, Workflow, Agent, model, Tool, Store, prompt, response, state, and
downstream evidence continues through ordinary Junjo telemetry.

Studio's Attempt-to-execution binding remains the canonical result/evidence
join. The telemetry context makes classification and inspection explicit; it
does not replace the ledger, copy traces into SQLite, or add work to the
ingestion authorization path.

## Coding-Agent Skill And Public Documentation

The SDK owns a distributable Junjo Evaluation skill following the Agent Skills
`SKILL.md` format. It contains instructions and small references, not transport
or runner implementation.

The skill teaches a coding agent to:

1. inspect the installed Junjo and Studio contract versions;
2. declare and list typed application targets;
3. create authored or generated cases;
4. lock a dataset;
5. execute and resume a clean source revision;
6. query failed or incomplete attempts;
7. retrieve exact evidence only when needed;
8. compare baseline and candidate runs; and
9. report progression, regression, uncertainty, and missing evidence.

Source-owned SDK documentation must include:

- installation and Studio configuration;
- target and evaluator declaration;
- CLI JSON and exit-status contracts;
- authored and generated dataset workflows;
- baseline/candidate comparison;
- interruption and resume;
- credential separation;
- telemetry classification;
- low-resource guidance; and
- one complete standalone-repository example.

AI Chat consumes these public interfaces as the primary reference application.
It does not carry a private copy of the skill or framework mechanics.

## Current-To-Target Migration Map

| Current AI Chat prototype | Product destination | What remains in AI Chat |
| --- | --- | --- |
| `evals/studio_models.py` | `junjo.studio` DTOs and public result types | Nothing generic |
| `evals/studio_client.py` | `junjo.studio` client and errors | Studio URL/token supplied through standard SDK configuration |
| `evals/runner.py` | `junjo.evaluation` runner, provenance, and generation flow | Application declarations only |
| Generic portions of `evals/targets.py` | SDK Node/Workflow/Agent target contracts | Typed inputs, dependency construction, real AI Chat entry points, and output projection |
| Generic portions of `evals/evaluators.py` | SDK evaluator contracts and built-ins | Local-place domain evaluator callback and rubric material |
| `evals/command.py` and `evals/__main__.py` | Installed `junjo eval` CLI | One explicit harness object importable by the CLI |
| Generic command/client/runner tests | SDK tests and contract fixtures | AI Chat declaration and live application E2E tests |

The migration is a cutover, not a compatibility layer. Once an SDK slice owns
a generic behavior and its tests pass, delete the AI Chat copy in the same
slice.

## Delivery Plan

Work proceeds in order. Each slice must reach its exit gate before the next
slice expands scope.

### Slice 0 — Preserve The Walking-Skeleton Evidence

Status: complete.

Keep the existing Studio schema, API, UI, tests, and recorded low-resource
evidence intact while productization proceeds. Treat AI Chat-local framework
code as migration source, not accepted ownership.

Exit gate:

- root ADR 0013 and Studio ADR 010 express the accepted boundary;
- the Lean MVP is reopened for SDK productization;
- product user stories are the acceptance source; and
- this execution plan is accepted.

### Slice 1 — Productize The Studio Client And DTOs

Status: complete.

Move the strict DTOs, typed errors, pagination, bounded HTTP transport,
evidence resolution, and comparison projections into `junjo.studio`.

Add SDK/Studio OpenAPI contract tests before deleting the AI Chat client and
DTO copies. Preserve one long-lived async client per command or harness
lifetime.

Exit gate:

- a standalone Python test project can authenticate and perform every existing
  evaluation-control operation through the installed SDK;
- request and response models match Studio OpenAPI;
- pending evidence and ambiguous execution identities remain distinct;
- idempotent retries and conflicts are tested;
- no Studio runtime module is an SDK dependency; and
- the AI Chat client and DTO copies are removed.

### Slice 2 — Productize The Harness With One Node Vertical

Status: implementation and deterministic validation complete. The final
credentialed live proof is part of Slice 5.

Implement `EvaluationHarness`, immutable context, source-revision provenance,
runner state machine, evaluator contracts, and `NodeTarget`.

Convert the AI Chat focused date-response Node to a small application
declaration and run one locked dataset through the SDK harness. Add the bounded
evaluation-attempt telemetry contract in the same vertical slice so the first
supported execution retains normal AI Chat service identity.

Exit gate:

- the SDK validates input before provider work;
- the real Node runs through `evaluate_node()`;
- execution is bound before evaluation;
- subject, evaluator, and result-write failures remain distinct;
- an interrupted bound Attempt is not executed again;
- one complete Node trace resolves from the Attempt in Studio;
- the app service identity remains truthful; and
- generic Node runner/evaluator/context code is absent from AI Chat.

### Slice 3 — Complete Workflow, Agent, And Generated Cases

Status: implementation and deterministic validation complete.

Add `WorkflowTarget` and `AgentTarget` using their real public lifecycles.
Move generated-case coordination and the remaining reusable target behavior
into the SDK.

AI Chat supplies one end-to-end Workflow declaration and one direct Agent
declaration. Authored and generated cases use the same SDK harness and result
contract.

Exit gate:

- Node, Workflow, and Agent cases share one runner and Attempt state machine;
- generated cases retain exact source execution and clean source revision;
- output is never silently promoted to expected truth;
- downstream evidence remains inspectable for complete Workflow and Agent
  traces;
- resume never duplicates an already-bound subject; and
- no generic target, evaluator, generation, or provenance mechanics remain in
  AI Chat.

### Slice 4 — Deliver The Agent Interface And Scoped Credential

Status: implementation and component validation complete.

Ship the installed `junjo eval` command, JSON schemas, stable error/exit
contract, explicit harness loading, scoped Studio token, public runbook, and
Junjo Evaluation skill.

Use the same public SDK methods exercised by application code. Do not create a
second CLI service layer.

Exit gate:

- a coding agent can list targets, create and lock a dataset, execute or resume
  a run, compare two runs, and retrieve exact evidence without a browser;
- the control/query token is separate from ingestion authority;
- secrets are redacted and never passed as ordinary command arguments;
- stdout is machine JSON and diagnostics use stderr;
- CLI and Python API produce equivalent typed results; and
- the skill delegates all mechanics to supported SDK and CLI operations.

### Slice 5 — Standalone And AI Chat Product Proof

Status: package-boundary, greenfield migration, productized authored
Node/Workflow/Agent, generated-Workflow, terminal-resume, comparison, evidence,
and ordinary-application CLI-to-Studio proofs complete. A deliberate live
mid-run interruption remains covered deterministically rather than repeated
against the provider.

Build the SDK artifact and install it into a clean standalone-style application
checkout. Do not use a monorepo-relative source import.

Repeat the complete AI Chat local-place baseline/candidate proof with Node,
Workflow, and Agent targets. Exercise authored and generated cases, interruption
and resume, evidence retrieval, and comparison through the public CLI.

Exit gate:

- the standalone application contains only explicit target/evaluator
  declarations and application construction;
- AI Chat imports no private Studio client, DTO, runner, or CLI implementation;
- baseline and candidate pair by exact locked case identity;
- every trustworthy execution resolves to all received Studio evidence with
  readiness and integrity explicit;
- ordinary non-evaluation AI Chat remains usable and correctly classified; and
- the coding-agent skill can drive the loop using only published Junjo
  documentation.

### Slice 6 — Low-Resource And Release Readiness

Status: complete. Deterministic validation, the greenfield migration reset,
clean-volume Compose, live authored and generated evaluations, ordinary
application telemetry, full component gates, and bounded small-profile
measurements are green.

Run the full validation owned by every changed component and repeat the
small-profile resource proof at runner concurrency one.

Measure:

- SDK runner maximum RSS;
- Studio backend idle and active RSS/CPU;
- evaluation REST latency and SQLite contention;
- ordinary trace-query latency;
- ingestion throughput and RSS;
- trace/evidence readiness; and
- telemetry loss, backpressure, and error counts.

Exit gate:

- no material ingestion-path regression is introduced;
- no unbounded query or response is found;
- resource measurements satisfy the accepted deployment budget or a measured
  exception is reviewed before release;
- SDK, Studio, telemetry contract, public docs, AI Chat, and packaging gates
  pass; and
- the coordinated release notes describe the new public SDK/Studio contract
  and credential separation.

## Kanban

### Done

- Accepted SDK ownership and application execution boundary.
- Accepted the bounded evaluation telemetry context and version decision.
- Productized the strict Studio client and DTOs in `junjo.studio`.
- Productized the SDK-owned Node, Workflow, and Agent evaluation harness,
  sequential runner, provenance, evaluators, generated-case coordination, and
  bounded telemetry context in `junjo.evaluation`.
- Added the installed JSON-first `junjo eval` CLI and separately scoped
  Studio evaluation tokens.
- Added the Studio token-management UI and read-only evaluation result views.
- Removed AI Chat's generic Studio client, DTO, runner, target, evaluator, and
  command ownership; AI Chat now declares only application targets, resources,
  projectors, fixtures, and its domain judge.
- Shipped the coding-agent skill and public SDK documentation.
- Built a Junjo wheel, installed it into the workspace-excluded standalone
  application, listed targets through the installed CLI, and executed its
  Node, Workflow, and Agent targets successfully.
- Validated SDK, backend, frontend, AI Chat, ingestion, telemetry contracts,
  documentation, package metadata, and the public surface.
- Replaced the unreleased Studio migration history with one generated
  greenfield initial revision covering all current models; validated empty
  upgrade, schema drift, Agent targets, token indexes, downgrade, and
  re-upgrade.
- Started Studio from an empty data directory; created separate ingestion and
  CLI credentials through authenticated management APIs; and used only the
  public SDK CLI to create and lock a three-case local-place realism Dataset.
- Executed baseline and same-revision repeat runs over authored Node, Workflow,
  and Agent targets. Both passed three of three; the comparison paired exact
  Case identities; and all six attempts resolved to distinct received traces
  with exact runtime identity and zero evidence diagnostics.
- Generated a Case from a real Workflow through the public CLI, retained its
  source execution and revision, ran it successfully, and proved terminal
  resume does not re-execute it.
- Started ordinary AI Chat against the same Studio deployment, created a
  contact, completed a Turn, and resolved its 13-span trace with no evaluation
  context or evidence diagnostics.
- Completed the coordinated release validation: 379 SDK tests, 950 Studio
  backend tests with 3 expected skips, 37 ingestion tests, 245 Studio frontend
  tests, 27 AI Chat frontend tests, strict typing, lint, production builds,
  OpenAPI contracts, telemetry contracts, generated documentation, repository
  invariants, package build, and Twine validation.
- Preserved the prior walking-skeleton live proof and low-resource record.
- Created durable Horizon 3 product user stories.
- Reopened the Lean MVP for SDK productization.
- Accepted this implementation plan.

### Next

- Review and commit the coordinated SDK, Studio, AI Chat, and documentation
  changes before starting the release workflow.

### Deferred

- MCP server;
- cross-language evaluation harnesses;
- broad historical evidence cohorts;
- prompt-template or state-schema hashing;
- automatic trace alignment;
- generalized replay;
- distributed scheduling or attempt leasing;
- executor concurrency above one; and
- automatic source changes or promotion.

## Validation Matrix

| Boundary | Required validation |
| --- | --- |
| Python SDK | Ruff, full pytest, strict `ty`, Griffe public-surface validation, documentation export/parity, package build, and Twine validation |
| Studio backend | Model, repository, migration, authentication, API contract, idempotency, concurrency, exact membership, and bounded-input tests |
| Studio frontend | OpenAPI contract tests, token-management tests, evaluation list/detail/compare tests, semantic-link tests, lint, build, and production bundle validation |
| Telemetry contract | Schema and fixture regeneration, producer and consumer conformance, unchanged generated-tree proof, and explicit version decision |
| AI Chat | Declaration/unit tests, real Node/Workflow/Agent live proof, application tests, Ruff, strict `ty`, Compose startup, frontend usability, and ordinary telemetry proof |
| Full system | Clean-volume Studio startup, built-SDK standalone install, dataset authoring, baseline/candidate execution, resume, evidence resolution, comparison, and low-resource measurements |
| Documentation and skill | Repository invariants, relative-link validation, public docs assembly/parity, skill validation, and one clean coding-agent walkthrough |

No component's green unit suite is sufficient evidence for a cross-system
slice.

## Release And Cutover Rules

- Build and validate the SDK artifact before the standalone proof.
- Coordinate SDK, Studio, telemetry-contract, documentation, and AI Chat
  changes in one compatibility-reviewed release sequence.
- Do not publish docs that claim the SDK harness or CLI exists before the
  corresponding package artifact is available.
- Do not retain an AI Chat compatibility runner after the SDK cutover.
- Do not change the evaluation API silently; use the versioned API and typed
  incompatibility error.
- Preserve the walking-skeleton tests until equivalent SDK and standalone E2E
  coverage has passed.
- Release only after the low-resource proof and ordinary application telemetry
  proof are both green.

## Definition Of Done

This productization plan is complete when:

- the published Junjo Python package owns every generic evaluation mechanism;
- AI Chat contains only application-specific declarations and domain behavior;
- Node, Workflow, and Agent targets run through one SDK harness;
- authored and generated datasets can be created, locked, rerun, and compared;
- results bind to exact Studio evidence with readiness and integrity explicit;
- evaluation traffic is explicit without replacing application identity;
- a coding agent can operate the loop through stable JSON commands and the
  published skill;
- control/query and ingestion credentials remain separate;
- no new ingestion hot-path work or unbounded evidence hydration exists;
- a standalone application proves the package boundary;
- full cross-component and low-resource validation passes; and
- the coordinated SDK and Studio release is ready to publish.

MCP and the other deferred capabilities are not part of this completion gate.
