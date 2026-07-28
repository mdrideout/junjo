# Horizon 3 Evaluation: Lean MVP Critical Path

- Status: Active implementation planning
- Date: 2026-07-27
- Owners: Junjo platform
- Parent strategy:
  [Junjo Agent Layer Strategy And Roadmap](AGENT_LAYER_ROADMAP.md)
- Horizon 3 north star:
  [Queryable Evaluation System And Iterative MVP Plan](AGENT_LAYER_HORIZON_3_QUERYABLE_EVALUATION.md)

## Purpose

The Horizon 3 north-star plan describes the eventual queryable evaluation
system. This document defines the smallest useful product we can build first.
It is the implementation-sequencing source of truth until the Lean MVP is
complete.

The goal is not to model every possible evaluation entity, recover prompt
templates, fingerprint application schemas, or build a generalized replay
engine. The goal is to prove one complete loop with the systems Junjo already
has:

1. create a dataset and add cases programmatically;
2. pull the cases into real application code;
3. execute a Node or Workflow through its normal Junjo lifecycle;
4. export ordinary telemetry to Studio;
5. record one evaluation outcome linked to the exact execution;
6. run the same cases against a labeled candidate; and
7. inspect the result and all received trace evidence in Studio.

If this loop is useful, later Horizon 3 work can generalize it from measured
needs. If it is not useful, we should learn that before changing shared
telemetry, ingestion, or SDK contracts.

## MVP Product Statement

The Lean MVP lets a developer or coding agent create a small immutable dataset
in Studio, run it from an AI Chat source checkout against the real application
code at that revision, and see pass, score, reason, duration, and a link to
Studio's received execution evidence for every case.

The first proof covers:

- one focused Node target through `evaluate_node()`;
- one end-to-end Workflow target through AI Chat's real application entry
  point;
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
end-to-end execution. Agent support does not prove another control-plane
boundary and is the first post-MVP target.

## Lean Scope Reset

### Required Now

- small Studio-owned dataset and result records;
- authenticated REST operations for a local application runner;
- an explicit AI Chat target adapter keyed by a small application-owned name;
- existing Junjo execution APIs and `ExecutionCorrelation`;
- existing OTLP trace export and Studio `TraceEvidence`;
- existing semantic execution resolution and deep links;
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
- evaluator definitions, evaluator registries, and evaluator DSLs;
- judge, verifier, and subject role spans in a shared telemetry contract;
- cross-trace or multi-root case membership;
- generic replay inferred from telemetry;
- Studio-side execution of application code;
- MCP, a generalized CLI, and cross-language runners;
- Agent target adapters;
- deterministic real-place verification beyond the existing qualitative judge;
- scoped personal access tokens;
- Studio-directed automatic source changes, promotion, or rollback; and
- a new ingestion index, cache, service, database, or queue.

Deferral does not reject these capabilities. It prevents them from blocking the
first useful evaluation loop.

## Foundation We Reuse

The MVP does not start from zero:

- AI Chat already owns live cases, application composition, judges, and result
  artifacts.
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

These are the critical path. The MVP should compose them rather than introduce
another execution or evidence path.

The existing AI Chat live evals already prove that real Node, Workflow, and
Agent execution works. We do not need another app-only discovery phase. The
first implementation slice begins where value is currently missing: a dynamic
dataset and centralized Studio result ledger.

## Accepted Boundaries Preserved

The Lean MVP stays within current accepted decisions:

- ADR 0007 owns the semantic execution reference and delayed Studio
  resolution.
- ADR 0010 keeps cases, judges, rubrics, and reports out of the Junjo runtime
  while preserving real Node lifecycle through `evaluate_node()`.
- ADR 0012 keeps the Studio integration trace-only.
- Studio remains the owner of diagnostic evidence queries, while AI Chat owns
  construction and execution of its application targets.

Two focused decisions are required before Slice 1: one root ownership ADR for
the cross-system application-harness/Studio/evidence boundary, and one Studio
ADR for canonical persistence, authenticated API semantics, exact execution
binding, indexes, and low-resource limits. No existing ADR needs to be silently
widened.

## Application Repository Is The Execution Host

The first useful coding-agent loop runs from the repository that owns the
application. For the vertical proof, that is the AI Chat checkout. The coding
agent has the checked-out source, Junjo SDK dependency, application types,
provider credentials, target construction, evaluators, and ordinary developer
tools required to make and validate a candidate. Studio does not need access to
the source tree and cannot reconstruct those dependencies from telemetry.

The system has three cooperating planes:

| Plane | MVP owner | Responsibility |
| --- | --- | --- |
| Code and execution | Coding agent plus deterministic AI Chat harness in the application checkout | Edit application source, validate cases, construct real dependencies, invoke Junjo execution, evaluate outputs, and flush telemetry |
| Evaluation control | Studio REST API and `junjo.db` | Own datasets, cases, runs, attempts, source revisions, outcomes, and exact execution bindings |
| Execution evidence | Existing OTLP ingestion, Parquet, execution resolver, and `TraceEvidence` | Receive and return all supported trace and span evidence without copying it into evaluation tables |

The coding agent may choose the source change and invoke the harness, but the
harness remains deterministic application code. It validates the Studio case,
selects an explicit target adapter, runs the real target, binds the resulting
execution to the pre-created attempt, runs the application-owned evaluator,
and records the terminal result. This avoids embedding control-plane behavior
in the Junjo runtime or letting an LLM improvise result-write semantics.

The minimum repeated loop is:

1. check out a clean, committed AI Chat candidate revision;
2. invoke the application-owned eval command for a locked Studio dataset;
3. receive the exact ordered cases and pre-created attempt IDs from Studio;
4. execute and record each case sequentially through the real application;
5. query the completed run as structured JSON;
6. resolve interesting attempt execution references and request their complete
   received `TraceEvidence`;
7. edit and validate ordinary application source;
8. commit the next candidate revision; and
9. rerun the same locked dataset and compare by case.

The baseline run remains stored in Studio. It does not need to be rerun for
every candidate unless the dataset, evaluator, model, or external execution
environment materially changes.

### Minimum Values Crossing The Application Boundary

The runner does not need a new Junjo runtime object. It needs two small
application-local values:

| Value | Minimum contents |
| --- | --- |
| Attempt context from Studio | `application_key`, `dataset_id`, `attempt_id`, `run_id`, `case_id`, `target_kind`, `target_key`, `input_version`, `input_json`, `expectation_json`, `evaluator_key`, `evaluator_version`, `candidate_label`, and run `source_revision` |
| Target execution returned by the adapter | evaluator subject, duration or error, and the semantic execution tuple whenever a trustworthy runtime ID exists |

The authoritative evaluation service namespace and service name come from one
runner configuration value shared by the OpenTelemetry Resource and semantic
execution references. They are not supplied independently on every case.

The data travels through two existing-purpose channels:

| Channel | Data |
| --- | --- |
| Studio REST | Small dataset, run, attempt, execution-binding, result, resolver, and evidence-query records |
| OTLP | The complete ordinary Junjo trace and span payload |

No dataset payload, score, rubric, candidate label, or Studio credential is
added to every Junjo span for the MVP. No trace payload is sent through the
evaluation REST API. This is why neither the Junjo SDK contract nor ingestion
hot path needs to change.

## Smallest Valuable End-To-End Flow

```text
Coding agent in AI Chat checkout
        |
        | invoke deterministic application harness
        v
Studio eval REST API <----> junjo.db control records
        |
        | start run; return exact cases + attempt IDs
        v
AI Chat target adapters
        |
        | evaluate_node() / real application Workflow entry point
        v
Normal Junjo execution ----> normal OTLP ingestion ----> Parquet evidence
        |                                                   ^
        | bind runtime ID; then record score + reason        |
        v                                                   |
Studio case attempt ----> execution resolver ---------------+
        |
        | explicit evidence request
        v
Coding agent or existing Studio evidence pages
```

Studio does not send code to the runner. The runner does not upload traces.
The runner receives small case definitions, executes application-owned code,
and returns small result metadata plus the semantic execution reference.
Telemetry continues through the existing OTLP path.

## Minimal Domain Model

The MVP needs four control-plane records and one embedded reference type.

### Dataset

A dataset is the exact case set used for comparison.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable ID |
| `key` | Stable application-facing key |
| `application_key` | Application/harness owner, initially `ai_chat` |
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
| `case_key` | Unique human-readable key within the dataset |
| `ordinal` | Stable execution and display order |
| `origin` | `authored` or `generated` |
| `target_kind` | `node` or `workflow` |
| `target_key` | Application-owned runner dispatch key |
| `input_version` | Application-owned positive integer version of the target input contract |
| `input_json` | Bounded application input validated by the runner |
| `expectation_json` | Optional bounded evaluator input |
| `evaluator_key` | Application-owned evaluator dispatch key |
| `evaluator_version` | Application-owned positive integer evaluator contract version |
| `source_execution` | Optional real execution that generated this case |
| `source_revision` | Required clean application Git revision for a generated source execution |
| `created_at` | Server timestamp |

The MVP does not define a universal input schema. `target_key` selects an
explicit AI Chat adapter, and that adapter validates `input_json` with the
application's existing types before execution.

`application_key`, `target_key`, and `input_version` are the minimum dispatch
contract between Studio data and a particular application checkout. They do
not turn Studio into a Python import registry or require Studio to understand
the application's schemas.

`expectation_json` is application-owned evaluator material. Studio stores and
returns it but does not interpret it as a general rubric language.

`evaluator_key` and `evaluator_version` pin the small application-owned
judgment contract used for every run of the locked case. The runner rejects an
unknown version. There is no Studio evaluator registry or DSL. Changing an
evaluator contract requires a new dataset; otherwise baseline/candidate scores
could appear comparable while being produced by different rules.

`source_execution` and case `source_revision` are either both present for a
generated case or both absent for an authored case. This makes the evidence and
application/SDK revision that generated a dataset case queryable together.

### Evaluation Run

A run applies one labeled candidate to one locked dataset.

Required fields:

| Field | Meaning |
| --- | --- |
| `id` | Server-owned stable ID |
| `dataset_id` | Exact locked dataset |
| `request_key` | Application-supplied idempotency key for starting/resuming this run |
| `candidate_label` | Required human-readable label such as `baseline` |
| `source_revision` | Required clean committed application Git revision |
| `status` | `active` or `completed` |
| `created_by_user_id` | Authenticated creator; nullable after user deletion |
| `created_at` | Server timestamp |
| `completed_at` | Server timestamp when every attempt is terminal |

These explicit labels are sufficient for the first comparison. They are not
pretended to be cryptographic candidate identity.

For a prompt experiment, the developer supplies the candidate label and runs
the command from the recorded source revision containing that prompt. The MVP
requires a clean committed worktree, captures `git rev-parse HEAD`, and rejects
a dirty candidate rather than attaching a misleading revision. The candidate
label is metadata; it does not select or inject different behavior. The exact
rendered model request remains in received trace evidence where the current
instrumentation emits it. The MVP neither reconstructs nor stores the
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
| `score` | Optional bounded score for a completed judgment |
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

The attempt record is authoritative for evaluation status, score, and reason.
Telemetry is authoritative for execution evidence. The MVP does not write a
second canonical result into span attributes or copy subject prompts,
responses, state, or traces into SQLite.

Execution binding and terminal judgment are separate idempotent writes. As soon
as the target returns a trustworthy runtime ID, the runner binds the semantic
execution reference to the pre-created attempt before invoking a potentially
slow or fallible judge. An identical retry succeeds and a conflicting rebind
returns a conflict. This preserves the evidence link if the runner stops after
execution but before judgment.

Recording the result is one atomic transition from `queued` to a terminal
status without changing the bound execution. When it is the final queued
attempt, the same transaction marks the run completed. An identical result
retry succeeds, a conflicting terminal write returns a conflict, and a
terminal attempt never reopens.

On command resume, an unbound queued attempt executes normally. A queued
attempt that already has `subject_execution` is never executed again: the
previous process completed execution but did not durably record a judgment.
The resumed command records a bounded `error` reason for that interrupted
attempt and continues. A fresh evaluation run is the explicit retry boundary.
This simple rule prevents duplicate provider work and competing semantic
execution bindings without adding attempt leases, persisted evaluator
subjects, or a distributed scheduler. Concurrent runners for the same run are
unsupported in the MVP.

If the runner dies before the runtime ID is durably bound, including the small
gap after application execution returns, the ordinary trace may be received
without evaluation membership and resume may execute the still-unbound
attempt. The dedicated service scope makes the orphan visually distinguishable
but is not canonical membership. Solving this crash window would require a new
trusted telemetry-to-attempt reconciliation contract and is not hidden inside
this MVP.

### Semantic Execution Reference

Both `source_execution` and `subject_execution` reuse ADR 0007 identity:

| Field | Meaning |
| --- | --- |
| `service_namespace` | Normalized service namespace |
| `service_name` | Normalized service name |
| `executable_type` | `workflow`, `subflow`, or `agent` |
| `runtime_id` | Exact Junjo executable runtime ID |

The UI links this reference to the existing semantic resolver. The runner does
not block waiting for a physical trace ID.

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

The first API should expose only the operations needed by the runner and the
read-only UI:

| Operation | Purpose |
| --- | --- |
| Create dataset | Create one draft |
| List datasets | Bounded programmatic discovery for a required `application_key` |
| Get dataset | Return metadata and ordered cases |
| Add case | Add one authored or generated case to a draft |
| Lock dataset | Irreversibly freeze the exact case set |
| Start run | Require a locked dataset and return attempts plus cases |
| Get attempt | Resume or inspect one pre-created attempt |
| Bind attempt execution | Idempotently attach an exact semantic execution as soon as its runtime ID exists |
| Record attempt result | Idempotently store one terminal case outcome |
| List evaluation runs | Discover bounded runs, optionally filtered by dataset |
| Get run | Return run, dataset summary, ordered cases, and attempts |
| Find execution membership | Resolve one exact semantic execution tuple to its case, dataset, run, and attempt role |

There is no update-case, delete-case, clone, cancel, retry, saved-search, bulk
import, or comparison endpoint in the MVP. Baseline and candidate comparison
is a small read projection over two completed runs for the same dataset and can
be added after both runs work.

Every route is authenticated and bounded. List endpoints are paginated from
the beginning even if the first demo has only a few rows.

Dataset creation is idempotent by `(application_key, key)`, case creation by
`(dataset_id, case_key)`, and run creation by
`(dataset_id, request_key)`. Repeating the same request and content returns the
same record; reusing that identity with different content returns a conflict.
Locking an already locked dataset succeeds. Starting the same run request
returns the original run and attempts. These semantics let a local command
resume after an uncertain HTTP response without duplicating work.

`Start run` returns the ordered immutable case definitions together with their
pre-created attempt IDs. `Get run` returns the same membership and current
statuses so the application runner can skip terminal attempts and distinguish
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
Attempt, and Semantic Execution Reference. The frontend adds Zod read schemas
only for the evaluation-run list and detail responses. Existing
`TraceEvidence`, execution-resolution, ingestion, and SDK structures do not
change.

The coding agent retrieves execution evidence by composing existing APIs:

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

The runner uses the existing Studio user sign-in flow to obtain a normal
session for the lifetime of the command. Credentials come from the runner's
environment and are never written into the dataset, result, trace, or logs.
The encrypted session cookie remains only in the command's in-memory cookie jar
and is discarded on exit. The runner does not call sign-out because Studio
sign-out intentionally invalidates every existing session for that user.

This is intentionally narrower than adding another credential system. The MVP
does not reuse the OTLP ingestion API key as a control-plane write credential.
A separately scoped personal access token can follow after the programmatic API
has stable operations and a demonstrated automation need.

Session reuse is limited to the local self-hosted proof and is not the durable
coding-agent authentication contract. Remote or unattended automation requires
a separately scoped evaluation-control token before it is supported.

## Programmatic Case Authoring

The API accepts cases from ordinary code. There is no browser upload or bundle.

An authored case supplies:

- `case_key`;
- `target_kind`;
- `target_key`;
- `input_version`;
- application input;
- optional expectation;
- `evaluator_key` plus `evaluator_version`; and
- no source execution.

The first execution of that case becomes the first subject evidence attached
through its case attempt. Historical selection and automatic input recovery are
post-MVP concerns.

## Real-Execution Dataset Generation

Dataset generation is a mode of the application runner, not a new ingestion
protocol.

For one generated case:

1. create or select a draft dataset;
2. verify a clean committed worktree and capture its revision;
3. choose the case key, known application input, and explicit evaluator
   key/version;
4. execute a direct Node with
   `ExecutionCorrelation(type="ai_chat.dataset_case", id=<dataset ID and case key>)`,
   or execute a real Turn through its existing `ai_chat.turn` correlation;
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

Direct Node evaluation executions use
`ExecutionCorrelation(type="ai_chat.eval_case", id=<attempt id>)`. Existing
propagation associates its nested Junjo executables with the case without
adding new per-span attributes.

Real Turn application entry points retain their existing `ai_chat.turn`
correlation for both dataset-generation and evaluation runs. The Studio dataset
and attempt records associate those Turn Workflow runtime IDs with the eval
case; they do not replace the application's domain identity. No run-class
telemetry contract is required for the MVP.

The runner uses a dedicated evaluation service name so its traces do not mix
with ordinary AI Chat service lists by default. Direct Node runs retain their
eval correlation, while real Turn runs are classified by the Studio control
record that references their truthful `ai_chat.turn` execution. This is
application resource configuration, not a shared telemetry-contract or
ingestion change.

AI Chat currently fixes its service scope in application constants. The runner
therefore adds one authoritative evaluation service-scope setting used by both
the OpenTelemetry Resource and every semantic execution reference. It must not
change only the Resource while resolver links keep the ordinary application
scope.

## AI Chat Runner

The first runner is an AI Chat-owned import surface and command, such as
`python -m ai_chat.evals`, not a Junjo SDK framework. It has four small,
explicit parts:

| Part | Responsibility |
| --- | --- |
| `StudioEvaluationClient` | Authenticate to Studio, exchange bounded evaluation DTOs, resolve an execution, and fetch `TraceEvidence`; it never executes application code or exports telemetry |
| Target adapters | Validate one known input version, construct real AI Chat dependencies, invoke the focused Node or real Turn entry point, and project the evaluator subject |
| Sequential runner | Start or resume a run, process unfinished attempts in ordinal order without rerunning a bound execution, bind execution, judge, record one terminal result, and continue after a case error |
| Dataset-generation operation | Reuse the same target adapters, retain source execution identity, and add a caller-curated case to a draft |

It owns a small explicit dispatch map:

| Target key | Adapter responsibility |
| --- | --- |
| Focused Node key | Validate initial state, construct fresh dependencies and Store, call `evaluate_node()` |
| Turn Workflow key | Validate use-case input, construct an isolated application, call the real Workflow entry point |

Each adapter returns:

- the semantic execution reference, whenever a trustworthy runtime ID exists;
- the evaluator subject value;
- duration; and
- any application-level execution error.

The focused adapter creates a fresh Node, Store, and dependency set for every
case and calls `evaluate_node()`. The Workflow adapter calls the real isolated
AI Chat application service entry point; it does not reconstruct Workflow
internals in a parallel eval-only implementation.

The runner authenticates, starts a new run or retrieves an interrupted run,
and processes attempts in stable ordinal order. An unbound queued attempt
executes; a bound queued attempt is finalized as interrupted without executing
again; and terminal attempts are skipped. Validation, dependency setup, target
execution, subject projection, and judge failures all produce a bounded
terminal `error` result, and one failed case does not abort the remaining run.
When execution identity exists, it is bound before the judge starts. The
runner then invokes the existing application-owned deterministic check or
quality judge selected by the case's exact evaluator key/version and records
the terminal attempt. The key/version dispatch is another small explicit map,
not a dynamic evaluator registry.

The command exposes only the operations needed for the proof:

- author a draft dataset and add explicit cases;
- generate a case through real application execution;
- lock a dataset;
- run or resume a locked dataset at the current clean revision; and
- fetch complete evidence for one attempt.

There is no plugin discovery, dynamic Python import, generalized target
registry, or Studio-side code execution.

The runner defaults to one case at a time. Controlled concurrency can be added
after measuring provider, memory, SQLite, and telemetry behavior.

The existing live pytest evals remain useful product-quality checks. The new
command may reuse their application composition and judges, but dynamic Studio
datasets should not be forced through pytest collection.

For runs created through the new Studio API, the runner records the canonical
attempt in Studio and does not also write a local result artifact. The existing
pytest suites may retain their current local artifacts because they are a
separate deliberate test surface, not a second result channel for the same
Studio run.

The core `junjo` package remains responsible for execution and telemetry, not
Studio authentication, evaluation datasets, HTTP DTOs, judges, or runner
coordination. If a second application later proves the Studio transport code is
repeated, extract the typed REST client and DTOs first into a separate
Studio-owned distribution. Target adapters, application schemas, dependency
composition, output projection, and evaluators remain application code.

## Stack Surface

| Area | MVP change | Why |
| --- | --- | --- |
| Studio frontend | Small read-only evaluation-run list/detail feature and existing trace links | Human inspection after the headless loop works |
| Studio backend | Four tables, one feature module, authenticated REST routes, migration | Canonical case/run coordination and result queries |
| Studio ingestion | No change | Ordinary OTLP telemetry already carries the evidence |
| Studio proto/gRPC | No change | Backend does not need a new ingestion control path |
| Python SDK | No change | Existing execution APIs, correlation, exporter, and results are sufficient; Studio control-plane code does not belong in core `junjo` |
| Telemetry contract | No change | Existing owner correlation, identity, parentage, and payload evidence are sufficient |
| AI Chat backend | Add the explicit command, thin Studio session client, sequential runner, authoritative eval service resource, and two small target adapters | The coding agent operates in this source checkout; application code owns construction, input validation, execution, and evaluation |
| AI Chat frontend | No change | Evals are deliberate developer operations, not end-user chat behavior |
| Deployment | No new service or port | The existing backend database and HTTP surface are reused |

This matrix is a constraint. A proposed first-slice change to ingestion, shared
telemetry schemas, or Junjo's public SDK must demonstrate why the existing
paths cannot complete the walking skeleton.

## Vertical Delivery Slices

Each slice must work end to end before starting the next.

### Slice 0: Accept The Lean Ownership Decision

Write two short ADRs.

The root ownership ADR covers:

- Studio owns canonical dataset, run, and judgment metadata;
- the application repository and its deterministic harness are the execution
  host for candidate code;
- applications own target construction, input validation, and evaluators;
- telemetry remains canonical execution evidence in Parquet;
- semantic execution references link control records to evidence;
- attempt execution binding is independent from terminal result recording;
- the local session client is a temporary self-hosted proof rather than the
  remote automation credential contract;
- no shared telemetry, ingestion, or SDK change is authorized by this MVP.

The Studio ADR covers:

- the four canonical tables in `junjo.db`;
- lock and idempotency semantics;
- flattened semantic execution identity and exact reverse lookup;
- separate execution-binding and terminal-result writes;
- authenticated programmatic routes and the temporary local-session boundary;
  and
- bounded pagination, JSON limits, indexes, and low-resource measurements.

Exit gate:

- both ADRs are accepted;
- the four records, evaluator identity, result authority, and
  execution-reference boundary are accepted;
- table ownership in `junjo.db` is accepted; and
- the deferred list is agreed.

### Slice 1: Headless Walking Skeleton

Implement:

- the four backend tables and migration;
- create dataset, add case, lock dataset, start run, get attempt/run, bind
  execution, record result, and exact execution-membership operations;
- an AI Chat Studio-session client;
- one focused date-response Node adapter; and
- the existing qualitative judge.

Demonstration:

1. create a draft dataset from Python;
2. add three authored local-place cases;
3. explicitly lock the dataset;
4. verify a clean worktree and start a run labeled `baseline` from its exact
   committed source revision;
5. execute each case through `evaluate_node()`;
6. bind and record three outcomes;
7. retrieve the completed run as structured data; and
8. resolve and fetch complete `TraceEvidence` for at least one attempt through
   the application client.

Exit gate:

- one command completes the entire loop;
- a stopped command resumes the same run without rerunning bound executions or
  touching terminal attempts;
- failed setup or execution produces an `error` attempt rather than a lost
  case;
- a draft cannot run and a locked dataset cannot accept cases;
- no local trace or result bundle is uploaded; and
- ingestion, telemetry contracts, and the SDK remain unchanged.

### Slice 2: End-To-End Candidate And Minimal Studio View

Implement:

- deliberate dataset-generation mode;
- one complete Turn Workflow adapter;
- optional source execution on cases;
- bounded evaluation-run list and detail APIs;
- one Studio Evaluation Runs list/detail surface; and
- a small client-side baseline/candidate read projection over two explicit run
  IDs.

Demonstration:

1. run three real Turn Workflows to create the local-place generated cases;
2. store their known inputs and source execution references in one draft;
3. explicitly lock the dataset;
4. run the exact same cases from the baseline source revision;
5. let the coding agent make and validate one prompt-only source change, commit
   it, and record its new source revision;
6. run the exact same cases with the named prompt candidate;
7. select those two run IDs and show pass, score, reason, and duration deltas;
   and
8. inspect all received evidence for both Workflow traces, including downstream
   effects.

Exit gate:

- an upstream prompt change can be evaluated by the final case outcome and
  investigated through all received evidence for both traces;
- a coding agent can perform the edit, commit, run, structured-result query,
  and explicit evidence-query loop from the AI Chat checkout without a browser
  or local result files;
- every result links to the correct execution;
- incomplete or delayed telemetry does not block recording the attempt; and
- a developer can inspect results without reading local JSON files;
- the frontend does not duplicate trace detail rendering; and
- pending telemetry is handled only after opening the existing semantic
  resolver, without per-row resolution fan-out;
- no automatic trace diff, prompt hash, or schema hash was required; and
- the full loop is usable on the supported low-resource deployment.

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
- one-case runner concurrency by default;
- exact execution resolution only when a link or detail is requested; and
- trace hydration only on an explicit Studio UI or application-client evidence
  request, never automatically for result lists or every case.

Before declaring Slice 2 complete, measure the supported small deployment while
an eval run records results:

- backend RSS and CPU;
- `junjo.db` write latency and lock contention;
- ordinary trace-query latency;
- ingestion throughput and RSS; and
- runner RSS at concurrency one.

Because ingestion code and protocol remain unchanged, any ingestion regression
is evidence of deployment contention rather than a new ingestion algorithm.
The measurement should confirm that distinction. This is one bounded
before/while-evaluation smoke on the supported small profile, not a broad
benchmark matrix.

## Validation

### Backend

- model and repository tests for all invariants;
- migration upgrade from the previous released database;
- authenticated API contract tests;
- atomic dataset locking and attempt creation;
- create/start idempotency and conflicting-content rejection;
- idempotent execution binding and terminal result recording;
- exact forward and reverse execution-membership lookup;
- generated-case source execution/revision all-or-none validation;
- evaluator key/version immutability and unknown-version rejection;
- bounded input and list tests; and
- concurrent final-attempt updates complete a run exactly once.

### AI Chat Runner

- deterministic client and dispatch tests with no provider calls;
- run resume executes only unbound queued attempts, marks a bound
  no-result attempt interrupted, and skips terminal attempts;
- execution binding survives a later judge or result-write failure;
- identical bind/result retries succeed and conflicting writes fail;
- input-validation failure creates an error attempt;
- Node and Workflow adapters return correct semantic references;
- execution resolution handles pending `404` and ambiguous `409` distinctly;
- explicit trace-evidence retrieval returns the resolved received evidence;
- generated output is never silently copied into the case expectation;
- generated cases retain the clean source revision that produced their source
  execution;
- one credentialed Node run;
- one credentialed generated Workflow dataset;
- baseline/candidate execution over the same dataset; and
- telemetry exporter flush and shutdown remain application-owned.

### Frontend

- response schemas match the backend OpenAPI contract;
- run list and detail loading states;
- active and completed runs plus pass, fail, error, and queued attempts;
- baseline/candidate presentation; and
- semantic execution links preserve the exact service and runtime identity.

### Full System

- run the Studio validation owned by every changed Studio area;
- run the AI Chat backend validation;
- start the supported Compose stack from a clean volume;
- create, execute, inspect, and compare a small dataset;
- run the same loop from a clean AI Chat application checkout through its
  coding-agent-facing command;
- confirm ordinary application executions remain usable; and
- record the low-resource measurements listed above.

## MVP Definition Of Done

Horizon 3 Lean MVP is complete when:

- cases can be added programmatically without uploading files;
- authored and real-execution-generated cases share one dataset contract;
- generated cases retain both their source execution and clean source
  revision;
- every locked case pins an application-owned evaluator key and version;
- an explicitly locked case set cannot change;
- Node and Workflow targets execute through real application code;
- baseline and candidate runs use that same case set;
- every case is visibly passed, failed, errored, or still queued;
- completed judgments have a score and reason;
- executions with a trustworthy runtime ID have exact semantic Studio links;
- all received trace evidence remains inspectable through existing pages;
- a local coding agent can create or retrieve a locked dataset, run or resume
  it, retrieve structured outcomes, and request attempt evidence without a
  browser or exported result file;
- a changed upstream prompt can be assessed at the final outcome and traced
  through downstream execution manually;
- the frontend provides a small readable result surface;
- ingestion and shared SDK/telemetry contracts did not change; and
- the supported low-resource deployment remains within its measured budget.

## Post-MVP Decision Order

Only after the MVP is used should we decide, in this order:

1. whether deterministic real-place verification materially improves the
   local-place eval;
2. whether to add the Agent target through the proven runner boundary;
3. whether scoped programmatic access tokens are needed;
4. whether dataset cloning or full version families are needed;
5. whether historical evidence needs automatic input projection;
6. whether descendant spans should become focused cases automatically;
7. whether state-schema identity solves a demonstrated comparison failure;
8. whether prompt-template identity solves a demonstrated comparison failure;
9. whether automated paired trace alignment is worth its complexity; and
10. whether repeated Studio transport code should become a separate typed
    Studio client distribution, while application adapters and evaluators stay
    in their application repositories.

This order keeps implementation pressure attached to demonstrated product
value rather than the completeness of the north-star model.
