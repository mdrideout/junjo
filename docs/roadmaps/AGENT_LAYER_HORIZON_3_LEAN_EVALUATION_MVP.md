# Horizon 3 Evaluation: Lean MVP Critical Path

- Status: Implemented and validated
- Date: 2026-07-27
- Owners: Junjo platform
- Parent strategy:
  [Junjo Agent Layer Strategy And Roadmap](AGENT_LAYER_ROADMAP.md)
- Horizon 3 north star:
  [Queryable Evaluation System And Iterative MVP Plan](AGENT_LAYER_HORIZON_3_QUERYABLE_EVALUATION.md)
- Product user stories:
  [Evaluation System User Stories](AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
- Accepted engineering plan:
  [SDK Evaluation Productization Plan](AGENT_LAYER_HORIZON_3_SDK_EVALUATION_PRODUCTIZATION_PLAN.md)
- Next UX slice:
  [Evaluation UX And Target Analysis Plan](AGENT_LAYER_HORIZON_3_EVALUATION_UX_AND_TARGET_ANALYSIS_PLAN.md)

## Purpose

The Horizon 3 north-star plan describes the eventual queryable evaluation
system. This document defines the smallest useful product we can build first
and the ownership correction required after validating its walking skeleton.
It owns Lean scope and product exit gates until the SDK-owned MVP is complete.
The accepted
[SDK Evaluation Productization Plan](AGENT_LAYER_HORIZON_3_SDK_EVALUATION_PRODUCTIZATION_PLAN.md)
owns the engineering execution order and migration backlog.

The goal is not to model every possible evaluation entity, recover prompt
templates, fingerprint application schemas, or build a generalized replay
engine. The goal is to prove one complete loop with the systems Junjo already
has:

1. create a dataset and add cases through the Junjo SDK or CLI;
2. let the SDK evaluation harness pull those cases into real application code;
3. execute a Node, Workflow, or Agent through its normal Junjo lifecycle;
4. export ordinary telemetry to Studio;
5. record one evaluation outcome linked to the exact execution;
6. run the same cases against a labeled candidate; and
7. inspect the result and all received trace evidence in Studio.

The application checkout remains the execution host because it owns the code
being evaluated. It does not own evaluation transport, DTOs, orchestration,
resume policy, CLI behavior, or generic target and evaluator mechanics. Those
are Junjo SDK product responsibilities.

The first application-local implementation proved that this loop is useful and
that the Studio persistence model is viable. It did not prove the correct
public product boundary. The MVP remains open until the generic mechanics are
productized in the SDK, AI Chat is reduced to domain declarations, and a coding
agent can operate the loop from a standalone application repository using
published Junjo interfaces and guidance.

## MVP Product Statement

The Lean MVP lets a developer or coding agent use the Junjo SDK and its
JSON-first CLI to create a small immutable dataset in Studio, load one explicit
evaluation declaration from an application checkout, run that dataset against
the real application code at a clean revision, and retrieve binary pass/fail
results, reasons, comparison data, and complete received execution evidence
for every case.

The first proof covers:

- one focused Node target through `evaluate_node()`;
- one end-to-end Workflow target through AI Chat's real application entry
  point;
- one Agent target through the same SDK-owned target contract;
- authored cases that have never run before;
- cases created from a deliberate real execution; and
- baseline versus one named candidate over the same locked case set.

The concrete value proof is AI Chat local-place realism:

- three prompts asking for a specific plausible place;
- the focused date-response Node;
- the complete Turn Workflow containing that behavior;
- the current baseline versus one prompt-only source change;
- the existing qualitative judge; and
- manual inspection of downstream effects through both received traces.

Node proves focused execution. Workflow proves upstream-to-downstream and
end-to-end execution. Agent proves that the public target contract covers all
first-class Junjo executable kinds without adding a second control-plane
boundary.

## Lean Scope Reset

### Required Now

- small Studio-owned dataset and result records;
- an SDK-owned typed Studio client and bounded DTOs;
- an SDK-owned evaluation harness, runner, resume/idempotency policy,
  evaluation context, target abstractions, and evaluator abstractions;
- a JSON-first, non-interactive Junjo CLI over those same public SDK APIs;
- authenticated REST operations suitable for local and unattended coding
  agents;
- a separately scoped Studio evaluation-control/query credential for remote or
  unattended agents, distinct from the OTLP ingestion credential;
- explicit application target declarations keyed by small application-owned
  names;
- application-owned dependency construction, input types, output projectors,
  and genuinely domain-specific evaluator callbacks;
- existing Junjo execution APIs and `ExecutionCorrelation`;
- a standardized evaluation telemetry context that retains the application's
  normal service identity;
- existing OTLP trace export and Studio `TraceEvidence`;
- existing semantic execution resolution and deep links;
- public runbooks and a coding-agent skill that operate the SDK and CLI rather
  than reimplementing framework policy;
- a minimal read-only Studio view after the headless loop works; and
- bounded inputs, outputs, list sizes, and runner concurrency.

### Explicitly Deferred

- prompt-template recovery, variable contracts, and prompt hashes;
- state-schema extraction and state-schema hashes;
- candidate, Graph, implementation, or artifact fingerprint systems;
- dataset families, mutable versions, branching, and merge behavior;
- automatic per-span case creation;
- a general evidence-entity taxonomy in the persisted MVP model;
- a projection DSL or arbitrary JSON Pointer API;
- broad historical cohort search and saved queries;
- historical-case import;
- automated trace alignment or causal diffing;
- a Studio-hosted evaluator registry or evaluator DSL;
- evaluator code execution inside Studio;
- cross-trace or multi-root case membership;
- generic replay inferred from telemetry;
- Studio-side execution of application code;
- MCP and cross-language runners;
- deterministic real-place verification beyond the existing qualitative judge;
- Studio-directed automatic source changes, promotion, or rollback; and
- a new ingestion index, cache, service, database, or queue.

Deferral does not reject these capabilities. It prevents them from blocking the
first useful evaluation loop.

## Foundation We Reuse

The SDK-owned MVP does not start from zero:

- AI Chat already proves application composition, domain input fixtures,
  provider construction, and domain-specific judgment callbacks.
- `evaluate_node()` already executes a real Node in a truthful one-Node
  Workflow and returns its evaluation Workflow runtime ID.
- `Workflow.execute()` and `Agent.execute()` already return exact runtime
  identity.
- `ExecutionCorrelation` already labels executable owner spans and propagates
  through nested Junjo execution.
- Studio already resolves service identity plus executable runtime ID to a
  trace, owner span, and diagnostic route.
- `TraceEvidence` already returns all received spans and verified Workflow,
  Agent, Store, operation, relationship, and integrity evidence for one trace.
- OTLP ingestion already preserves the attributes and parentage required for
  the execution tree.
- The validated Studio walking skeleton already proves immutable datasets,
  run/attempt coordination, exact execution membership, and bounded evidence
  retrieval on the supported small deployment.

These are the critical path. The MVP should compose them rather than introduce
another execution or evidence path.

The application-local prototype is evidence, not the reusable framework. Its
generic Studio client, DTOs, runner, target/evaluator mechanics, retry rules,
Git provenance, and CLI orchestration must move into the Junjo SDK. AI Chat
keeps only the declarations and callbacks that require AI Chat types or
dependencies.

## Accepted Boundaries Preserved

The Lean MVP requires a focused correction to current decisions:

- ADR 0007 owns the semantic execution reference and delayed Studio
  resolution.
- ADR 0010 keeps application cases and domain judgment policy out of the Junjo
  execution runtime while preserving real Node lifecycle through
  `evaluate_node()`. It does not prevent the Junjo SDK distribution from owning
  a higher-level evaluation client and harness.
- ADR 0012 keeps the Studio integration trace-only.
- Studio remains the owner of canonical evaluation records and diagnostic
  evidence queries.
- The Junjo SDK owns the complete evaluation framework and Studio interaction
  contract.
- Applications own only typed target declarations, real dependency
  construction, output projection, and domain evaluator callbacks.

Root ADR 0013 and Studio ADR 010 must state this corrected ownership before SDK
productization proceeds. The product stories in
[Evaluation System User Stories](AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
are the durable acceptance language for the developer and coding-agent
experience.

## Application Repository Hosts Execution; Junjo Owns The Harness

The coding-agent loop runs from the repository that owns the application. For
the vertical proof, that is the AI Chat checkout. The coding agent has the
checked-out source, Junjo SDK dependency, application types, provider
credentials, prompts, and ordinary developer tools required to make and
validate a candidate. Studio does not need access to the source tree and cannot
reconstruct those dependencies from telemetry.

Execution location does not determine framework ownership. The Junjo SDK
installed in that repository owns the Studio client, typed DTOs, dataset and
run operations, target/evaluator abstractions, sequential orchestration,
binding-before-judgment rule, resume/idempotency behavior, source-revision
capture, evaluation context, evidence queries, and CLI. The application
registers small typed declarations that tell the SDK how to construct and
execute its real objects.

The system has three cooperating planes:

| Plane | MVP owner | Responsibility |
| --- | --- | --- |
| Code and execution | Junjo SDK evaluation harness loaded in the application checkout | Coordinate cases and attempts, invoke declared targets, apply evaluator contracts, capture provenance, bind executions, record outcomes, and flush telemetry |
| Application binding | AI Chat target and evaluator declarations | Supply input types, construct real dependencies and executable objects, project outputs, and implement domain-specific checks that Junjo cannot infer |
| Evaluation control | Studio REST API and `junjo.db` | Own datasets, cases, runs, attempts, source revisions, outcomes, and exact execution bindings |
| Execution evidence | Existing OTLP ingestion, Parquet, execution resolver, and `TraceEvidence` | Receive and return all supported trace and span evidence without copying it into evaluation tables |

The coding agent may choose the source change and invoke the SDK harness, but
it does not improvise result-write semantics. The framework validates the
Studio envelope, resolves an explicit application declaration, runs the real
target, binds the resulting execution to the pre-created attempt, invokes the
declared evaluator, and records the terminal result. Application callbacks
never authenticate to Studio or own retry, persistence, telemetry, or CLI
policy.

The minimum repeated loop is:

1. check out a clean, committed AI Chat source revision;
2. invoke `junjo eval run execute` with an explicit application declaration;
3. let the SDK receive the exact ordered cases and pre-created attempt IDs from
   Studio;
4. let the SDK execute and record each case sequentially through the real
   application;
5. query the completed run through stable JSON output;
6. resolve interesting attempt execution references and request their complete
   received `TraceEvidence`;
7. edit and validate ordinary application source;
8. commit the next source revision; and
9. rerun the same locked dataset and compare by case.

The baseline run remains stored in Studio. It does not need to be rerun for
every candidate unless the dataset, evaluator, model, or external execution
environment materially changes.

### Minimum Values Crossing The Application Boundary

The SDK supplies the application callback with a typed evaluation context and
validated target input. The application returns a small target result:

| Value | Owner and minimum contents |
| --- | --- |
| `EvaluationContext` | SDK-owned immutable context containing application, dataset, run, case, attempt, source revision, run class, and execution role identities |
| Target declaration | Application-owned key/kind and input contract plus functions for construction/execution and output projection |
| Evaluator declaration | Application-owned key/version, expectation contract, and optional domain callback; generic binary judgment mechanics remain SDK-owned |
| Target result | SDK-owned result envelope containing evaluator subject, duration or error, and semantic execution identity whenever a trustworthy runtime ID exists |

The SDK derives the semantic service namespace and service name from the same
OpenTelemetry Resource used by the application. Evaluation mode must never
replace the application's normal service identity with an eval-only service
name.

The data travels through two existing-purpose channels:

| Channel | Data |
| --- | --- |
| Studio REST through the SDK client | Small dataset, run, attempt, execution-binding, result, resolver, comparison, and evidence-query records |
| OTLP | The complete ordinary Junjo trace and span payload |

No trace payload is sent through the evaluation REST API. The SDK creates one
bounded evaluation-attempt root span and propagates `EvaluationContext` while
the subject and optional judge execute. That root records standardized
evaluation identifiers and role metadata; child Junjo execution retains the
application's normal service identity and existing executable attributes. The
attempt ledger and semantic subject binding remain canonical. Evaluation
metadata is not duplicated onto every span.

This requires a small documented SDK/telemetry-contract addition, but no new
OTLP endpoint, synchronous ingestion lookup, per-span relational copy, or
change to Studio's ingestion hot path.

## Smallest Valuable End-To-End Flow

```text
Coding agent in an application checkout
        |
        | invoke JSON-first Junjo CLI
        v
Junjo SDK client + evaluation harness
        |                         ^
        | load explicit targets  | return subjects/errors
        v                         |
Application declarations --------+
        |
        | create/start/query through authenticated SDK client
        v
Studio eval REST API <----> junjo.db control records
        |
        | start run; return exact cases + attempt IDs
        v
SDK target abstraction + application construction callback
        |
        | Node / Workflow / Agent normal entry point
        v
Evaluation-attempt root span + normal Junjo execution
        |
        +--------------------> normal OTLP ingestion ----> Parquet evidence
        |                                                   ^
        | bind runtime ID; then record pass/fail + reason    |
        v                                                   |
Studio case attempt ----> execution resolver ---------------+
        |
        | explicit evidence request
        v
Junjo CLI/SDK, coding-agent skill, or existing Studio evidence pages
```

Studio does not send or execute code. The SDK harness does not upload traces
through REST. It receives small case definitions, calls explicitly declared
application construction/execution functions, and returns small result
metadata plus the semantic execution reference. Telemetry continues through
the existing OTLP path.

## Minimal Domain Model

The MVP needs four control-plane records and one embedded reference type.

### Dataset

A dataset is the exact case set used for comparison.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable ID |
| `key` | Stable application-facing key |
| `application_key` | Application identity, initially `ai_chat` |
| `name` | Human-readable name |
| `description` | Optional bounded description |
| `status` | `draft` or `locked` |
| `created_by_user_id` | Authenticated creator; nullable after user deletion |
| `created_at` | Server timestamp |
| `locked_at` | Timestamp of the explicit lock, when applicable |

A draft accepts new cases. Locking is an explicit irreversible operation. A
locked dataset never changes, and a run may start only from a locked dataset.
To change the case set during the MVP, create another dataset. This deliberately
replaces a full dataset-family and versioning model with one simple invariant.

The lock transaction uses `BEGIN IMMEDIATE`, rechecks that the dataset is still
a draft, and changes its status before committing. Add-case uses the same write
serialization boundary, preventing a real add-case/lock race without relying on
SQLite row-lock syntax.

### Case

A case tells one application runner which target to execute and with what
input.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable ID |
| `dataset_id` | Owning dataset |
| `case_key` | Unique machine-oriented idempotency key within the dataset |
| `evaluation_name` | Required human name describing what pass or fail tests |
| `ordinal` | Stable execution and display order |
| `origin` | `authored` or `generated` |
| `target_kind` | `node`, `workflow`, or `agent` |
| `target_key` | Application-owned declaration key resolved by the SDK harness |
| `target_name` | Human-readable target name snapshotted when the case is authored |
| `input_version` | Application-owned positive integer version of the target input contract |
| `input_json` | Bounded application input validated by the runner |
| `expectation_json` | Optional bounded evaluator input |
| `evaluator_key` | Application-owned evaluator dispatch key |
| `evaluator_version` | Application-owned positive integer evaluator contract version |
| `source_execution` | Optional real execution that generated this case |
| `source_revision` | Required clean application Git revision for a generated source execution |
| `created_at` | Server timestamp |

The MVP does not define a universal input schema. `target_key` selects an
explicit target declaration loaded by the SDK harness. The declaration
validates `input_json` with the application's existing type before execution.
Junjo owns the target abstraction and lifecycle; the application supplies the
type and the construction/execution callback.

`application_key`, `target_key`, and `input_version` are the minimum dispatch
contract between Studio data and a particular application checkout. They do
not turn Studio into a Python import registry or require Studio to understand
the application's schemas.

`target_name` is display metadata, not dispatch identity. The SDK derives it
from the registered target, and Studio stores it with the immutable case so
the UI can show the actual Node, Workflow, or Agent name while historical data
remains self-contained.

`expectation_json` is evaluator input. Studio stores and returns it but does
not interpret it as a general rubric language. The SDK owns evaluator
contracts and dispatch; an application supplies a callback only where the
judgment depends on its domain.

`evaluation_name` is required human-facing text such as `Response place
realism`. It explains what pass or fail means without exposing the
application's machine-oriented Case key as the product label.

`evaluator_key` and `evaluator_version` pin the SDK-loaded judgment contract
used for every run of the locked case. The SDK harness rejects an unknown
version. There is no Studio evaluator registry or DSL. Changing an evaluator
contract requires a new dataset; otherwise baseline/candidate results could
appear comparable while being produced by different rules.

`source_execution` and case `source_revision` are either both present for a
generated case or both absent for an authored case. This makes the evidence and
application/SDK revision that generated a dataset case queryable together.

### Evaluation Run

A run applies one labeled application revision to one locked dataset.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable ID |
| `dataset_id` | Exact locked dataset |
| `request_key` | Application-supplied idempotency key for starting/resuming this run |
| `run_label` | Required human-readable label such as `baseline` |
| `source_revision` | Required clean committed application Git revision |
| `status` | `active` or `completed` |
| `created_by_user_id` | Authenticated creator; nullable after user deletion |
| `created_at` | Server timestamp |
| `completed_at` | Server timestamp when every attempt is terminal |

These explicit labels are sufficient for the first comparison. They are not
pretended to be cryptographic candidate identity.

For a prompt experiment, the developer supplies the Run label and runs
the SDK command from the recorded source revision containing that prompt. The
SDK requires a clean committed worktree, captures `git rev-parse HEAD`, and
rejects a dirty checkout rather than attaching a misleading revision. The Run
label is metadata; it does not select or inject different behavior.
The exact rendered model request remains in received trace evidence where the
current instrumentation emits it. The MVP neither reconstructs nor stores the
originating template.

Starting a run creates one queued attempt for every case in a single
transaction. Those attempt rows are the exact membership snapshot for the run.
No separate dataset-version or run-manifest structure is required.

### Case Attempt

An attempt records one case outcome and its execution evidence reference.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable attempt ID |
| `run_id` | Owning evaluation run |
| `case_id` | Exact dataset case |
| `status` | `queued`, `passed`, `failed`, or `error` |
| `reason` | Optional bounded human-readable judgment or error |
| `duration_ms` | Optional non-negative duration |
| `subject_execution` | Optional exact semantic execution reference |
| `execution_bound_at` | Nullable timestamp set when execution identity is bound |
| `recorded_at` | Nullable while queued; server timestamp after terminal write |

`passed` and `failed` mean the application evaluator completed. `error` means
the target or evaluator did not produce a valid judgment. A missing
`subject_execution` is valid only when setup failed before Junjo created a
trustworthy execution identity. When a Workflow error exposes its run ID, the
attempt retains that reference even though execution failed.

The attempt record is authoritative for evaluation status and reason.
Telemetry is authoritative for execution evidence. The MVP does not write a
second canonical result into span attributes or copy subject prompts,
responses, state, or traces into SQLite.

Execution binding and terminal judgment are separate idempotent writes. As soon
as the target returns a trustworthy runtime ID, the SDK runner binds the semantic
execution reference to the pre-created attempt before invoking a potentially
slow or fallible judge. An identical retry succeeds and a conflicting rebind
returns a conflict. This preserves the evidence link if the runner stops after
execution but before judgment.

Recording the result is one atomic transition from `queued` to a terminal
status without changing the bound execution. When it is the final queued
attempt, the same transaction marks the run completed. An identical result
retry succeeds, a conflicting terminal write returns a conflict, and a
terminal attempt never reopens.

On SDK command resume, an unbound queued attempt executes normally. A queued
attempt that already has `subject_execution` is never executed again: the
previous process completed execution but did not durably record a judgment.
The resumed command records a bounded `error` reason for that interrupted
attempt and continues. A fresh evaluation run is the explicit retry boundary.
This simple rule prevents duplicate provider work and competing semantic
execution bindings without adding attempt leases, persisted evaluator
subjects, or a distributed scheduler. Concurrent runners for the same run are
unsupported in the MVP.

If the SDK runner dies before the runtime ID is durably bound, including the small
gap after application execution returns, the ordinary trace may be received
without evaluation membership and resume may execute the still-unbound
attempt. The standardized evaluation-attempt root can make the orphan
discoverable in telemetry but is not canonical membership. Solving this crash
window would require a new trusted telemetry-to-attempt reconciliation
contract and is not hidden inside this MVP.

### Semantic Execution Reference

Both `source_execution` and `subject_execution` reuse ADR 0007 identity:

| Field | Meaning |
| --- | --- |
| `service_namespace` | Normalized service namespace |
| `service_name` | Normalized service name |
| `executable_type` | `workflow`, `subflow`, or `agent` |
| `runtime_id` | Exact Junjo executable runtime ID |

The UI and SDK client link this reference to the existing semantic resolver.
The SDK runner does not block waiting for a physical trace ID.

For a Node case, `evaluate_node()` supplies the generated one-Node Workflow
runtime ID. The execution reference therefore uses executable type `workflow`.
The Node remains the logical target, while the truthful one-Node Workflow trace
is its evidence envelope.

## SQLite Changes

The first implementation adds four small canonical tables to Studio's existing
`junjo.db`:

- `eval_datasets`;
- `eval_cases`;
- `eval_runs`; and
- `eval_case_attempts`.

The tables use ordinary foreign keys, uniqueness constraints, timestamps, and
bounded serialized JSON fields. They are registered through the existing
SQLAlchemy model boundary. New models are imported from
`app/db_sqlite/models.py` and `backend/migrations/env.py`; the Alembic revision
is then generated programmatically through the existing autogenerate workflow
and is never hand-written.

Semantic execution references are stored as four nullable scalar columns on
the owning record, not opaque JSON:

- `eval_cases` has `source_service_namespace`, `source_service_name`,
  `source_executable_type`, and `source_runtime_id`; and
- `eval_case_attempts` has `subject_service_namespace`,
  `subject_service_name`, `subject_executable_type`, and
  `subject_runtime_id`.

All four columns are either present together or absent together. This keeps
forward links simple and makes exact reverse membership lookup possible
without scanning serialized values.

The minimum constraints and indexes follow actual MVP access paths:

- unique `(application_key, key)` dataset identity plus bounded dataset listing
  by `(application_key, created_at, id)`;
- unique `(dataset_id, case_key)` and `(dataset_id, ordinal)`;
- ordered cases by `(dataset_id, ordinal, id)`;
- unique `(dataset_id, request_key)`, global recent runs by
  `(created_at, id)`, and dataset-scoped runs by
  `(dataset_id, created_at, id)`;
- unique `(run_id, case_id)` attempts plus `(run_id, status)` and
  `(case_id, run_id)` lookup indexes;
- partial composite indexes over the four populated source-execution columns;
  and
- a partial unique composite index over the four populated subject-execution
  columns.

Creator foreign keys use nullable `ON DELETE SET NULL` behavior so deleting a
Studio user does not delete evaluation history or make user deletion fail.

The implementation does not change `metadata.db`. Evaluation records are
canonical product data, not rebuildable Parquet index metadata.

The implementation also does not create relational span, prompt, state, or
trace copies. Execution references remain small, and received evidence remains
in Parquet.

## Minimal REST API

The first API exposes only the operations needed by the SDK client, CLI, and
read-only UI:

| Operation | Purpose |
| --- | --- |
| Create dataset | Create one draft |
| List datasets | Bounded programmatic discovery for a required `application_key` |
| Get dataset | Return metadata and ordered cases |
| Add case | Add one authored or generated case to a draft |
| Lock dataset | Irreversibly freeze the exact case set |
| Start run | Require a locked dataset and return attempts plus cases to the SDK harness |
| Get attempt | Let the SDK resume or inspect one pre-created attempt |
| Bind attempt execution | Idempotently attach an exact semantic execution as soon as its runtime ID exists |
| Record attempt result | Idempotently store one terminal case outcome |
| List evaluation runs | Discover bounded runs, optionally filtered by dataset |
| Get run | Return run, dataset summary, ordered cases, and attempts |
| Find execution membership | Resolve one exact semantic execution tuple to its case, dataset, run, and attempt role |

There is no update-case, delete-case, clone, cancel, retry, saved-search, bulk
import, or arbitrary query endpoint in the MVP. Baseline and candidate
comparison is a deterministic SDK/UI projection over two completed runs for
the same dataset; it does not require duplicated comparison persistence.

Every route is authenticated and bounded. List endpoints are paginated from
the beginning even if the first demo has only a few rows.

Dataset creation is idempotent by `(application_key, key)`, case creation by
`(dataset_id, case_key)`, and run creation by
`(dataset_id, request_key)`. Repeating the same request and content returns the
same record; reusing that identity with different content returns a conflict.
Locking an already locked dataset succeeds. Starting the same run request
returns the original run and attempts. These semantics let the SDK runner
resume after an uncertain HTTP response without duplicating work.

`Start run` returns the ordered immutable case definitions together with their
pre-created attempt IDs. `Get run` returns the same membership and current
statuses so the SDK runner can skip terminal attempts and distinguish
unbound from already-bound queued attempts. Binding and terminal-result retries
follow the idempotency rules in the attempt model.

The critical write and lookup routes are deliberately separate:

```text
PUT /api/v1/evaluation/attempts/{attempt_id}/execution
PUT /api/v1/evaluation/attempts/{attempt_id}/result
GET /api/v1/evaluation/execution-membership
    ?service_namespace=...
    &service_name=...
    &executable_type=...
    &runtime_id=...
```

The membership response is bounded and reports whether the execution is a case
source or an attempt subject together with its dataset, case, run, and attempt
identity. It does not hydrate trace evidence.

The backend adds direct Pydantic write/read contracts for Dataset, Case, Run,
Attempt, and Semantic Execution Reference. The Junjo SDK owns the corresponding
public client DTOs and typed errors. The frontend adds Zod read schemas only
for the evaluation-run list and detail responses. Existing `TraceEvidence`,
execution-resolution, and ingestion structures remain reusable.

The SDK client retrieves execution evidence by composing existing APIs:

1. read the attempt's semantic execution reference;
2. call the existing `/api/v1/execution-resolution` endpoint;
3. treat `404` as telemetry not received or indexed yet and `409` as ambiguous
   identity requiring inspection; and
4. after resolution, call the existing
   `/api/v1/trace-evidence/{trace_id}` endpoint.

No new broad trace-query endpoint or automatic per-case evidence hydration is
required. The exact execution-membership operation supplies the reverse
control-plane lookup when the agent starts with a semantic runtime identity.
Starting with a trace ID, the agent first reads `TraceEvidence`, selects the
relevant exact executable-owner identity, and performs that same lookup.

### MVP Programmatic Authentication

The MVP uses a separately scoped developer access token for local, remote, and
unattended use. Human browser sessions create, list, copy, and delete tokens;
the SDK intentionally has no email/password sign-in path. The SDK accepts the
token through its normal configuration boundary, redacts it from output, and
never writes it into a
dataset, result, trace, or log. OTLP ingestion API keys never authorize
evaluation-control routes, and evaluation-control tokens never become
ingestion credentials.

## Programmatic Case Authoring

The SDK client and CLI accept cases from ordinary code or JSON input. There is
no browser upload or bundle.

An authored case supplies:

- `case_key`;
- `target_kind`;
- `target_key`;
- SDK-derived `target_name`;
- `input_version`;
- application input;
- optional expectation;
- `evaluator_key` plus `evaluator_version`; and
- no source execution.

The first execution of that case becomes the first subject evidence attached
through its case attempt. Historical selection and automatic input recovery are
post-MVP concerns.

## Real-Execution Dataset Generation

Dataset generation is a mode of the SDK evaluation harness, not application
framework code and not a new ingestion protocol.

For one generated case:

1. create or select a draft dataset;
2. verify a clean committed worktree and capture its revision;
3. choose the case key, known application input, and explicit target and
   evaluator declarations;
4. let the SDK establish a `dataset_generation` evaluation context and execute
   the declared Node, Workflow, or Agent through its normal entry point;
5. let normal OTLP telemetry reach Studio;
6. retain the returned top-level runtime ID;
7. add the case to the draft with its input, expectation, evaluator identity,
   source revision, and semantic source execution reference.

The observed output is source evidence, not automatically accepted truth.
Generation never copies that output into `expectation_json` and silently
blesses the application's current behavior. The caller must supply or curate
the deterministic constraint, rubric, or expected value separately.

The source execution points to the received evidence envelope:

- a focused Node uses its truthful one-Node Workflow trace;
- a Workflow uses all evidence received for its top-level Workflow trace.

All received descendant Nodes, Agents, model operations, Tools, Subflows,
Stores, and transitions remain available through `TraceEvidence`. The MVP does
not create one database row per descendant and does not automatically turn
every descendant into an independently runnable case.

This gives the developer a labeled end-to-end evidence set now. Promoting one
descendant into a focused case can be added later when a real repeated workflow
demonstrates the required input projection.

The SDK establishes an evaluation-attempt root span with bounded standardized
attributes for run class (`evaluation` or `dataset_generation`), dataset, run,
case, attempt, source revision, and role (`subject`, `judge`, `verifier`, or
`orchestrator`) as applicable. The declared target executes beneath that
context while retaining the same service namespace, service name, and domain
correlation it has during ordinary application use. Studio control records
remain the canonical membership and result source.

## Junjo SDK Evaluation Harness And CLI

The productized harness is a Junjo SDK public surface with six explicit parts:

| Part | Responsibility |
| --- | --- |
| Studio client and DTOs | Authenticate, exchange bounded evaluation records, resolve membership, fetch evidence, and expose typed errors |
| Evaluation harness | Load one explicit application declaration and validate target/evaluator keys and versions before provider work |
| Target abstractions | Define consistent Node, Workflow, and Agent execution and return the SDK target-result envelope |
| Evaluator abstractions | Provide common result contracts and invoke a domain callback only when application semantics require it |
| Evaluation executor | Own one lazy application runtime, start/resume sequentially, execute only eligible attempts, bind before judgment, record results, and continue after case errors |
| Dataset generation | Reuse declared targets, retain source execution identity, and add a curated case to a draft |

AI Chat owns only a small declaration:

| Declared item | Application responsibility |
| --- | --- |
| Focused date-response Node | Supply the input type and construct fresh dependencies, Store, and Node |
| Turn Workflow | Supply the use-case input type and construct the isolated real entry point |
| Agent proof | Supply the Agent input type and construct the real Agent and dependencies |
| Local-place evaluator | Supply the domain judgment callback and expectation type |

The SDK Node target calls `evaluate_node()` around the application-supplied
Node and Store. The SDK Workflow and Agent targets call the supplied real
entry points. All return the same SDK-owned result envelope: evaluator subject,
duration or error, and semantic execution identity when a trustworthy runtime
ID exists.

The SDK runner processes attempts in stable ordinal order. An unbound queued
attempt executes; a bound queued attempt is finalized as interrupted without
executing again; terminal attempts are skipped. Validation, setup, execution,
projection, and judgment failures produce a bounded terminal `error`, and one
case error does not abort the run. The SDK binds execution before invoking the
declared evaluator.

The CLI is a thin adapter over the same public Python APIs:

- `junjo eval dataset create|list|get|add|lock`;
- `junjo eval case generate`;
- `junjo eval run execute|resume|list|get|compare`;
- `junjo eval attempt get|evidence`; and
- `junjo eval execution membership`.

Execution commands require one explicit `module:object` application
declaration rather than plugin discovery. Data output is versioned JSON by
default; diagnostics go to standard error; commands are non-interactive; exit
codes distinguish usage, authentication, conflict, execution, evaluation, and
pending evidence; idempotency keys and run IDs are accepted explicitly; and
secrets are redacted. An optional human projection does not replace the tested
JSON contract.

The coding-agent skill and public runbook operate these commands to create and
lock datasets, run clean baseline/candidate revisions, resume safely, compare
outcomes, and retrieve exact evidence. MCP may later wrap the same SDK client,
but it is not a second implementation and does not block the CLI MVP.

Runner concurrency defaults to one. Controlled concurrency follows measured
provider, memory, SQLite, and telemetry behavior.

Existing live pytest evals remain useful product-quality checks, but dynamic
Studio datasets are not forced through pytest collection. Studio runs record
their canonical results only in Studio; existing pytest suites may keep their
separate deliberate local artifacts.

AI Chat must not retain a private Studio client, duplicate DTOs, generic
runner, retry policy, Git provenance logic, CLI orchestration, or generic
target/evaluator machinery. It retains only typed inputs, dependency
construction, real entry-point calls, output projection, fixtures, and domain
evaluator callbacks.

## Stack Surface

| Area | MVP change | Why |
| --- | --- | --- |
| Studio frontend | Small read-only evaluation-run list/detail feature and existing trace links | Human inspection after the headless loop works |
| Studio backend | Four tables, one feature module, authenticated REST routes, migration | Canonical case/run coordination and result queries |
| Studio ingestion | No change | Ordinary OTLP telemetry already carries the evidence |
| Studio proto/gRPC | No change | Backend does not need a new ingestion control path |
| Python SDK | Add Studio client/DTOs, harness, runner, Node/Workflow/Agent targets, evaluator contracts, evaluation context, provenance, evidence/comparison queries, and CLI | Junjo provides one batteries-included agent-facing product contract |
| Telemetry contract | Add one bounded evaluation-attempt root-span/context contract | Classify evaluation and dataset-generation traces without replacing application service identity or duplicating attributes on every span |
| AI Chat backend | Replace the prototype framework with a small target/evaluator declaration | The application owns only code and domain behavior Junjo cannot supply |
| AI Chat frontend | No change | Evals are deliberate developer operations, not end-user chat behavior |
| Public docs and agent skill | Add setup, declaration, dataset/run/evidence workflows, JSON examples, and invariants | A coding agent in a standalone application repository must operate the product without monorepo knowledge |
| Deployment | No new service or port | The existing backend database and HTTP surface are reused |

This matrix is a constraint. The SDK and bounded evaluation telemetry changes
are required corrections. No ingestion service, protobuf, cache, database, or
new runtime service is implied.

## Vertical Delivery Slices

Each slice must work end to end before starting the next.

### Slice 0: Preserve The Validated Walking Skeleton

The application-local prototype already proved the Studio schema, API,
read-only UI, Node/Workflow execution loop, binding-before-judgment rule,
resume behavior, evidence links, candidate comparison, and low-resource
viability. Keep that evidence and its tests while explicitly rejecting the
prototype's AI Chat ownership as the final public architecture.

Exit gate:

- the completion record is framed as prototype evidence;
- Studio persistence and APIs remain reusable;
- root ADR 0013 and Studio ADR 010 state SDK ownership; and
- the user stories are the acceptance source for productization.

### Slice 1: Productize The SDK Framework

Implement the public Studio client/DTOs, evaluation context, harness, runner,
provenance, Node/Workflow/Agent target contracts, evaluator contracts,
evidence/comparison queries, and typed failure model in `junjo`.

Move generic tests from AI Chat to the SDK. Replace AI Chat's private
framework with one explicit declaration and domain callbacks.

Exit gate:

- no generic Studio/evaluation mechanics remain under `ai_chat`;
- a second minimal fixture application can use the same SDK APIs;
- all three executable target kinds use one attempt lifecycle;
- resume and idempotency tests pass in the SDK; and
- SDK public-surface, package, type, lint, and test gates pass.

### Slice 2: Deliver The Agent-Facing Interface

Implement the JSON-first `junjo eval` command groups, stable output/version and
exit-code contracts, explicit declaration loading, scoped evaluation-control
authentication, public runbook, and coding-agent skill. Add the bounded
evaluation-attempt telemetry context while retaining normal application
service identity.

Exit gate:

- commands are non-interactive and machine-readable without parsing prose;
- an agent can create/lock a dataset, execute/resume a run, compare runs, and
  query exact attempt evidence;
- secrets never appear in stdout, stderr, Studio records, or telemetry;
- the skill delegates mechanics to the CLI/SDK and contains no hidden
  framework implementation; and
- telemetry contract, SDK producer, Studio consumer/query, and docs validate
  together.

### Slice 3: Repeat The Full AI Chat Proof

Use the published-style SDK interface from a clean AI Chat checkout. Create the
same authored and generated cases, run a committed baseline and prompt-only
candidate through Node, Workflow, and Agent targets, compare them, and inspect
all received downstream evidence through both CLI JSON and Studio.

Exit gate:

- the loop needs no monorepo-relative imports or AI Chat-owned client/runner;
- every result links to the correct application-service execution;
- incomplete telemetry does not block result recording and pending evidence is
  explicit;
- the read-only frontend continues to reuse existing evidence views;
- ordinary application telemetry remains correctly identified;
- no automatic trace diff, prompt hash, or schema hash is required; and
- the full loop remains usable on the supported low-resource deployment.

The frontend is read-only in the MVP. Programmatic authoring is the primary
contract. A dataset-management UI follows only if regular use shows it is
valuable.

## Low-Resource Rules

The Lean MVP preserves the current low-resource architecture:

- no changes in the Rust ingestion hot path;
- no synchronous backend call added to OTLP export;
- no new span index or per-span evaluation rows;
- no trace payload copies in SQLite;
- no default trace cache;
- no background evaluator or scheduler service;
- no unbounded dataset, case, run, or result lists;
- one-case SDK runner concurrency by default;
- one bounded evaluation-attempt root rather than repeated evaluation
  attributes on every descendant span;
- normal application service identity during evaluation;
- exact execution resolution only when a link or detail is requested; and
- trace hydration only on an explicit Studio UI or application-client evidence
  request, never automatically for result lists or every case.

Before declaring Slice 3 complete, repeat measurement on the supported small
deployment while
an eval run records results:

- backend RSS and CPU;
- `junjo.db` write latency and lock contention;
- ordinary trace-query latency;
- ingestion throughput and RSS; and
- runner RSS at concurrency one.

Because ingestion code and protocol remain unchanged, any ingestion regression
is evidence of deployment contention or telemetry volume, not a new ingestion
algorithm. The measurement should confirm that distinction. This is one
bounded before/while-evaluation smoke on the supported small profile, not a
broad benchmark matrix.

## Validation

### Backend

- model and repository tests for all invariants;
- greenfield migration upgrade from an empty database, downgrade to base, and
  re-upgrade to head;
- authenticated API contract tests;
- atomic dataset locking and attempt creation;
- create/start idempotency and conflicting-content rejection;
- idempotent execution binding and terminal result recording;
- exact forward and reverse execution-membership lookup;
- generated-case source execution/revision all-or-none validation;
- evaluator key/version immutability and unknown-version rejection;
- bounded input and list tests; and
- concurrent final-attempt updates complete a run exactly once.

### Python SDK Framework And CLI

- deterministic Studio client, DTO, harness, target, evaluator, and dispatch
  tests with no provider calls;
- run resume executes only unbound queued attempts, marks a bound
  no-result attempt interrupted, and skips terminal attempts;
- execution binding survives a later judge or result-write failure;
- identical bind/result retries succeed and conflicting writes fail;
- input-validation failure creates an error attempt;
- Node, Workflow, and Agent targets return correct semantic references;
- execution resolution handles pending `404` and ambiguous `409` distinctly;
- explicit trace-evidence retrieval returns the resolved received evidence;
- generated output is never silently copied into the case expectation;
- generated cases retain the clean source revision that produced their source
  execution;
- one credentialed Node run;
- one credentialed generated Workflow dataset;
- baseline/candidate execution over the same dataset; and
- evaluation context produces one bounded root, retains application service
  identity, and propagates through subject/judge execution;
- JSON output schemas and exit codes remain stable across every CLI command;
- stdout contains data only and credentials are always redacted;
- public SDK surface, lint, type, test, package-build, and Twine gates; and
- telemetry exporter flush and shutdown remain SDK-harness responsibilities.

### AI Chat Binding

- the declaration contains no Studio transport, DTO, retry, persistence,
  provenance, or CLI code;
- application input validation and dependency construction use real AI Chat
  types and composition;
- output projectors and domain evaluator callbacks are explicit;
- one credentialed Node, generated Workflow, and Agent execution; and
- baseline/candidate execution over the same dataset.

### Frontend

- response schemas match the backend OpenAPI contract;
- run list and detail loading states;
- active and completed runs plus pass, fail, error, and queued attempts;
- baseline/candidate presentation; and
- semantic execution links preserve the exact service and runtime identity.

### Full System

- run the Studio validation owned by every changed Studio area;
- run the AI Chat backend validation;
- run the SDK's complete validation and telemetry conformance suite;
- exercise the public runbook and coding-agent skill from a clean
  published-style application checkout;
- start the supported Compose stack from a clean volume;
- create, execute, inspect, and compare a small dataset;
- run the same loop from a clean AI Chat application checkout through
  `junjo eval`;
- confirm ordinary application executions remain usable; and
- record the low-resource measurements listed above.

## MVP Definition Of Done

Horizon 3 Lean MVP is complete when:

- Studio client, DTOs, harness, runner, retry/resume policy, provenance,
  evaluation context, target/evaluator abstractions, and CLI are public Junjo
  SDK product surfaces;
- AI Chat contains only typed target declarations, construction/execution
  callbacks, projectors, fixtures, and domain evaluator callbacks;
- cases can be added programmatically without uploading files;
- authored and real-execution-generated cases share one dataset contract;
- generated cases retain both their source execution and clean source
  revision;
- every locked case pins an SDK-loaded evaluator key and version;
- an explicitly locked case set cannot change;
- Node, Workflow, and Agent targets execute through real application code;
- baseline and candidate runs use that same case set;
- every case is visibly passed, failed, errored, or still queued;
- completed judgments have a binary result and reason;
- executions with a trustworthy runtime ID have exact semantic Studio links;
- all received trace evidence remains inspectable through existing pages;
- a coding agent in a standalone application repository can use stable
  JSON-first commands to create or retrieve a locked dataset, run or resume it,
  compare structured outcomes, and request exact evidence without a browser,
  exported result file, or monorepo knowledge;
- public docs and the coding-agent skill teach that flow and defer all mechanics
  to the SDK/CLI;
- evaluation telemetry is distinguishable through standardized context while
  retaining the application's normal service identity;
- a changed upstream prompt can be assessed at the final outcome and traced
  through downstream execution manually;
- the frontend provides a small readable result surface;
- the bounded SDK/telemetry contract changed coherently across schemas,
  producer, Studio query behavior, conformance tests, and docs, while the
  ingestion hot path and protobuf plane did not change; and
- the supported low-resource deployment remains within its measured budget.

## Walking-Skeleton Validation Record

The first end-to-end walking skeleton was implemented and validated on
2026-07-27. It proves product value, Studio persistence, evidence linkage, and
low-resource viability. It does **not** complete the Lean MVP because generic
framework mechanics were placed in AI Chat rather than the Junjo SDK. Preserve
the evidence below while replacing that prototype ownership in Slices 1–3.

Delivered:

- initial cross-platform and Studio decisions establishing
  application-executed, Studio-controlled evaluation records;
- Studio-owned Dataset, Case, Evaluation Run, and Case Attempt persistence,
  migrations, authenticated bounded REST APIs, idempotency rules, and
  concurrency controls;
- an AI Chat application-local prototype of the client, command, runner, Node
  and Workflow adapters, authored/generated cases, run/resume behavior,
  binding-before-judgment, result recording, and evidence retrieval;
- read-only Studio run list, run detail, and baseline/candidate comparison
  pages with exact semantic execution links; and
- prototype-isolated evaluation telemetry under
  `junjo.examples / ai-chat-evals`.

The prototype did not change ingestion behavior, Studio protobufs, the shared
telemetry contract, or Junjo SDK core execution APIs. Productization replaces
its eval-only service identity with standardized SDK evaluation context under
the application's normal service identity.

Validation completed:

- all Studio validation gates passed, including 940 backend tests with three
  skips, 237 frontend tests, production frontend build, ingestion validation,
  telemetry-contract conformance, and protobuf staleness checks;
- all 83 AI Chat backend tests passed with Ruff, strict `ty`, and lockfile
  validation;
- the Python SDK passed Ruff, 329 core tests, strict `ty`, Griffe public-surface
  validation, package build, and Twine validation;
- the repository invariant validator and `git diff --check` passed;
- migration validation exercised previous revision to head, downgrade, and
  re-upgrade while preserving an existing user; and
- independent final reviews found no material backend, application-harness,
  frontend-contract, documentation, or cross-component contract defect.

The isolated live proof used one locked three-case dataset containing two
authored focused Node cases and one case generated by a real Workflow
execution. A clean committed baseline and a prompt-only candidate both
completed with three of three attempts passed over identical case IDs and
ordinals. All six attempts resolved to received evidence: Node executions had
three spans and Workflow executions had nine. Each semantic reference exactly
matched its owner span runtime ID and the evaluation resource scope. The
baseline and candidate rendered-prompt hashes differed, only candidate evidence
contained the candidate directive, and the generated Workflow case retained
its source execution and source revision. The complete ledger and evidence
links survived two graceful Studio backend restarts.

Ordinary AI Chat was also started from a fresh isolated Compose project. A
contact and avatar were created, a real turn was admitted and completed, the
conversation remained queryable, the frontend and application endpoints
returned successfully, and its 13-span Workflow resolved in Studio under the
ordinary application scope.

The following values are a bounded local small-profile smoke, not a capacity
benchmark:

| Signal | Observed result |
| --- | --- |
| Studio backend | 302.8 MiB RSS idle; 314.2 MiB during evaluation at about 1.0% CPU; 324.6 MiB highest later query sample, below the 450 MiB limit |
| Ingestion | 43.5 MiB RSS idle; 62.4 MiB during evaluation at about 1.64% CPU |
| Evaluation executor (sequential) | 118,046,720 bytes baseline maximum RSS; 119,341,056 bytes candidate maximum RSS |
| Final-run ingestion | 36 spans over 55.36 seconds, or 0.650 spans/second, dominated by provider latency |
| Ingestion authentication | 28 export requests; 13 cache hits; 15 backend-validation misses; zero invalid validations |
| Trace evidence | 8.4–51.4 ms per query; 16.9 ms mean |
| Evaluation reads and writes | 4.2 ms run detail; 5.6 ms dataset lock; 7.9 ms idempotent run start; 3.9 ms result write |
| Contention and loss | Zero backend SQLite lock/busy errors; zero ingestion warnings, errors, drops, or backpressure rejections |

The accepted proof was run without out-of-process access to the live SQLite WAL
and used only supported application and Studio APIs. Both isolated Compose
projects, volumes, networks, credentials, evidence artifacts, and the temporary
source checkout were removed afterward. The pre-existing Studio deployment
retained its original containers and remained healthy.

## SDK-Owned Live Validation Record

The productized SDK-owned path was revalidated on 2026-07-29 after replacing the
unreleased Studio migration history with one greenfield initial revision.
Studio started from an empty data directory, upgraded directly to revision
`65bb30ac331d`, and created every application and evaluation table. An
independent empty database also passed upgrade, downgrade, re-upgrade, and
`alembic check`.

The attended setup used only supported product boundaries:

- browser-session management APIs created one OTLP ingestion API key and one
  separately scoped Evaluation token;
- the SDK CLI authenticated with `JUNJO_AI_STUDIO_CLI_TOKEN`, discovered the
  application harness, and reported Node, Workflow, and Agent targets;
- the CLI created and irreversibly locked dataset
  `local-place-realism-v1` with three authored real-geography Tests, all named
  `Response place realism`; and
- a clean committed temporary checkout executed two labeled runs through the
  SDK runner while the application exported ordinary telemetry to the same
  Studio deployment.

Both `baseline` and `current` completed three of three attempts with passing
binary judgments. The Runs independently selected real Prospect Heights and
Barclays-area places including Weather Up, Leland Eating and Drinking House,
Unnameable Books, Chuko, Hungry Ghost Coffee, Grand Army Plaza, and Prospect
Park. Studio's comparison paired all three rows by exact locked Test identity
and reported unchanged binary results.

All six attempts resolved through `junjo eval attempt evidence` to six distinct
trace IDs. Bound and resolved runtime IDs matched exactly, all evidence
diagnostic lists were empty, and the received traces contained 7 spans for
each focused Node case, 13 for each Workflow case, and 7 for each Agent case.
Focused Node evaluation intentionally binds the generated one-Node Workflow
created by `evaluate_node()`; the Dataset target remains `node`.

The same SDK-owned CLI also created a second Dataset from a real generated
Workflow execution. Its Case retained the exact source execution and clean
source revision, the locked Dataset reran successfully, and
resuming the completed Run did not re-execute its terminal Attempt. The
sequential runner reached 118,505,472 bytes maximum RSS for this run.

Ordinary AI Chat was then started from the same checkout and Studio deployment.
After one upstream Gemini high-demand `503`, a retry created a real contact and
completed a real Turn. Studio resolved its 13-span Workflow by exact runtime
ID with no evidence diagnostics. None of those ordinary spans carried
evaluation context, confirming that application and evaluation traffic remain
distinguishable without changing the application's service identity.

The clean-volume post-run snapshot used 276.9 MiB for the Studio backend under
its 450 MiB limit, 71.48 MiB for ingestion, and 10.11 MiB for the production
frontend. The Studio data directory was 1.1 MiB. Backend and ingestion logs
contained no error, panic, authentication-failure, drop, or unavailable
records. This is a bounded functional smoke, not a throughput benchmark.

## Post-MVP Decision Order

Only after the corrected SDK-owned MVP is used should we decide, in this order:

1. whether deterministic real-place verification materially improves the
   local-place eval;
2. whether MCP materially improves agent operation beyond the JSON-first CLI;
3. whether dataset cloning or full version families are needed;
4. whether historical evidence needs automatic input projection;
5. whether descendant spans should become focused cases automatically;
6. whether state-schema identity solves a demonstrated comparison failure;
7. whether prompt-template identity solves a demonstrated comparison failure;
8. whether automated paired trace alignment is worth its complexity; and
9. whether higher runner concurrency is justified by measured workloads.

This order keeps implementation pressure attached to demonstrated product
value rather than the completeness of the north-star model.
