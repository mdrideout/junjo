# ADR-010: Evaluation control persistence and API

## Status

Accepted

## Date

2026-07-27

## Context

Root ADR 0013 assigns Studio ownership of bounded evaluation datasets, runs,
attempts, outcomes, and semantic execution membership, while the Junjo SDK
owns the Studio client, DTOs, complete evaluation harness, runner, CLI,
target/evaluator abstractions, and evaluation context. An application supplies
only typed target declarations, real dependency construction, output
projection, and domain-specific evaluator callbacks. Complete trace evidence
continues to use Studio's existing OTLP, Parquet, execution-resolution, and
`TraceEvidence` paths.

Studio needs a small canonical data model and authenticated API that a local
or remote SDK harness can safely retry. It must preserve the one-vCPU/1GB
deployment profile, avoid per-span relational copies, and keep canonical
product data out of the rebuildable telemetry metadata database.

## Decision

### Canonical records live in `junjo.db`

Studio stores four canonical record types in the existing application
database:

- Dataset: one named application-scoped draft or locked input corpus;
- Case: one ordered, named evaluation, versioned application input, and
  SDK-loaded evaluator contract;
- Run: one labeled clean source revision applied to one locked dataset; and
- Attempt: one case membership and outcome within that run.

These records live in `junjo.db` because they are user-created product state.
They never live in rebuildable `metadata.db`. Full prompts, responses, state,
span records, and trace payloads remain in Parquet and are not copied into
these tables.

Creator references use nullable `ON DELETE SET NULL` semantics so evaluation
history survives user deletion.

### The evaluation release resets the greenfield migration baseline

Studio is still greenfield and does not provide an upgrade contract for
existing application data. The evaluation release replaces the prior Alembic
history with one initial revision generated from the complete current model
metadata. That single revision creates users, ingestion API keys, evaluation
tokens, datasets, cases, runs, and attempts together.

Existing Studio data volumes are intentionally incompatible with this reset.
Developers and preview deployments must delete their Studio application data
and initialize a fresh database. We do not retain migration complexity,
compatibility shims, or a partial upgrade path for data that the product has
not committed to preserving.

### Datasets lock irreversibly

A draft accepts cases. A locked dataset never changes and is the only dataset
state from which a run may start. Changing inputs, target or evaluator contract
versions, expectations, or generated-source provenance requires a new dataset.

Dataset locking and case insertion use one SQLite write-serialization boundary
and recheck state inside the transaction. This prevents add-case/lock races
without pretending SQLite provides row locks.

Dataset creation is idempotent by application key plus dataset key. Case
creation is idempotent by dataset plus case key. Repeating identical content
returns the existing record; conflicting content returns an explicit conflict.

### Cases retain application dispatch and provenance

A Case stores bounded JSON input and optional expectation material plus:

- a required human evaluation name describing what pass or fail means;
- origin (`authored` or `generated`);
- target kind (`node`, `workflow`, or `agent`) and application-owned target
  declaration key;
- positive input-contract version;
- SDK-loaded evaluator key and positive version;
- stable ordinal; and
- for generated cases, both the clean source revision and exact source
  execution identity.

Studio stores and validates the envelope but does not interpret application
input, expectation, target, or evaluator semantics. The SDK harness resolves
the target/evaluator keys against one explicit application declaration and
rejects unknown versions before provider work.

### Semantic execution references are indexed scalar fields

Source and subject execution identities reuse ADR 0007's exact tuple:

- normalized service namespace;
- service name;
- executable type;
- runtime ID.

Each tuple is either wholly present or wholly absent. The values are stored as
scalar columns, not serialized JSON, so exact forward and reverse membership
queries use bounded indexes.

Source execution identity may be shared by multiple cases. Subject execution
identity is unique across attempts in the Lean MVP because every case run owns
a fresh application execution.

Studio does not eagerly resolve semantic identities to trace IDs for list
responses. A caller explicitly composes execution resolution and
`TraceEvidence` when evidence is requested.

### Run start snapshots exact membership

A run may start only for a locked, non-empty dataset. One transaction creates
the run plus one queued attempt for every ordered case. The start response
returns those attempt IDs with the exact case definitions needed by the
SDK harness.

Run start is idempotent by dataset plus bounded application request key.
Repeating the same content returns the original run and attempts; conflicting
content returns an explicit conflict.

### Execution binding and result recording are separate

Binding an attempt execution is an idempotent write that accepts one complete
semantic execution tuple. An identical retry succeeds. A conflicting rebind
returns a conflict.

Recording an attempt result is a separate atomic transition from queued to
`passed`, `failed`, or `error`. An identical retry succeeds; a conflicting
terminal result or attempt reopening returns a conflict. The final terminal
attempt marks its run complete in the same transaction.

A result may omit execution identity only when setup failed before Junjo
created a trustworthy runtime ID. Passed and failed judgments require a bound
execution and bounded reason. Errors retain a bound execution whenever one
exists. Evaluation judgments are binary; Studio stores no numeric score,
mean score, confidence, or score delta.

### The HTTP surface is authenticated and bounded

The MVP API provides only:

- create, list, and get Dataset;
- add Case and lock Dataset;
- start, list, and get Run;
- get Attempt;
- bind Attempt execution;
- record Attempt result; and
- exact reverse execution-membership lookup.

The SDK client and JSON-first CLI are the primary programmatic consumers. List
routes use cursor pagination and explicit maximum page sizes. Text and
JSON inputs have declared byte limits. There is no update, delete, clone,
cancel, lease, retry, bulk import, arbitrary query DSL, or automatic evidence
hydration in this decision.

All routes require an authenticated Studio user. Evaluation control is a
deployment-shared resource in the MVP: any authenticated user may add or lock
Cases, start Runs, and bind or finalize Attempts. `created_by_user_id` is audit
provenance, not an object-level access-control boundary. This matches Studio's
current shared-resource model and must be revisited with the separately scoped
remote automation credential rather than implied by creator ownership.

Human users manage developer access tokens through an ordinary encrypted
Studio browser session. The management surface returns each stored bearer
credential so it can be copied again and deletes the credential when the user
removes it. This deliberately matches Studio's existing Application Telemetry
API key UX: anyone with an authenticated Studio browser session already shares
credential-management authority. CLI and SDK automation use the separately
scoped access tokens and do not accept Studio account passwords. Plain HTTP is
accepted only for loopback use; remote Studio origins require HTTPS.
Application Telemetry API keys never authorize these routes, and developer
access tokens never authorize ingestion.

### Evaluation context complements the ledger

The SDK creates one bounded evaluation-attempt root span and propagates an
evaluation context around Node, Workflow, or Agent subject execution and any
judge or verifier. The context identifies run class, dataset, run, case,
attempt, candidate revision, and execution role. It retains the application's
normal OpenTelemetry service identity and domain correlation; an eval-only
service name is not the product contract.

Studio does not copy that context onto every relational span row. The Attempt
binding remains canonical membership, and the existing resolver plus
`TraceEvidence` returns the complete received trace. The context makes
evaluation and dataset-generation telemetry explicit without redesigning the
four tables or ingestion hot path.

### Agent queries compose bounded APIs

A coding agent uses the SDK client or CLI to list/get datasets and runs,
compare two runs over one dataset, resolve exact execution membership, and
request evidence for selected attempts. Comparison is a deterministic
projection over run detail, not new persisted state. The API does not add an
arbitrary query DSL or eagerly hydrate evidence. MCP may later wrap the same
SDK client; it is not a second Studio contract.

### Frontend reads results without duplicating evidence views

The Studio UI provides bounded Dataset, Run, and comparison views. Dataset
Cases present their human evaluation name and prominent Node, Workflow, or
Agent scope. Run results present binary status, reason, and a concise
**View spans** link. Machine keys, evaluator versions, source provenance, and
the exact Git commit remain available as technical details rather than primary
table columns.

The UI follows the existing semantic resolver for telemetry. It does not
resolve every list row, copy trace detail rendering, or hydrate
`TraceEvidence` until the user explicitly requests evidence.

### Low-resource behavior is a release requirement

The implementation adds no ingestion work, background evaluator, scheduler,
queue, per-span evaluation table, trace cache, or second database service.
SDK runner concurrency defaults to one. Evaluation context adds one bounded
root span rather than duplicating evaluation attributes onto every descendant.

Indexes are limited to declared dataset, ordered-case, recent-run,
run-attempt, case-history, and exact execution-membership access paths.
Before the complete Workflow slice is released, the supported small deployment
must measure backend CPU/RSS, SQLite write latency and lock contention,
ordinary trace-query latency, ingestion throughput/RSS, and runner RSS while
an evaluation run records results.

## Consequences

- Studio becomes the canonical evaluation ledger while keeping execution
  evidence in its existing hot/cold telemetry architecture.
- SDK commands can retry uncertain writes without duplicating
  datasets, cases, runs, bindings, or outcomes.
- Exact execution membership is queryable in both directions without scanning
  JSON or resolving every trace.
- Locked datasets make baseline/candidate comparison truthful and simple.
- The MVP intentionally lacks mutation, distributed leasing, retry-in-place,
  generalized evaluator definitions, and automatic trace reconciliation.
- Node, Workflow, and Agent targets share the same Studio record and query
  model; target construction remains outside Studio.
- Coding agents receive a bounded query surface through the SDK/CLI without
  granting Studio access to application source or execution credentials.
- Existing pre-evaluation Studio application data must be deleted once at this
  greenfield cutover; subsequent schema changes start from the single initial
  revision.

## Rejected alternatives

- Put evaluation records in `metadata.db`: canonical user data must not
  disappear when a rebuildable index is recreated.
- Store semantic references as JSON: reverse lookup would require serialized
  scans and weaken all-or-none constraints.
- Store trace IDs eagerly: telemetry can arrive later and physical identities
  are not the canonical application link.
- Hydrate trace evidence in run lists: this creates query fan-out and spends
  memory without an explicit evidence request.
- Add per-span evaluation membership: one attempt-to-execution binding already
  reaches complete received trace evidence.
- Add attempt leases and concurrent workers: the first harness is deliberately
  sequential and local.
- Reuse OTLP API keys for REST writes: ingestion authorization and evaluation
  control are separate authorities.
- Keep the Studio client, DTOs, runner, and CLI inside AI Chat: these are Junjo
  product mechanics and would force every application to reimplement policy.
- Introduce MCP before a stable SDK/CLI: MCP may be a later adapter, not a
  second client or orchestration implementation.

## Related decisions

- [Root ADR 0013: Application-executed Studio evaluations](../../../../docs/adr/0013-application-executed-studio-evaluations.md)
- [Root ADR 0007: Application execution correlation and Studio resolution](../../../../docs/adr/0007-execution-correlation-and-studio-resolution.md)
- [Root ADR 0014: Bounded evaluation telemetry context](../../../../docs/adr/0014-evaluation-telemetry-context.md)
- [Studio ADR 007: Agent execution diagnostics](007-agent-execution-diagnostics.md)
- [Studio ADR 009: Bounded ingestion API-key validation](009-bounded-ingestion-api-key-validation.md)
- [Horizon 3 Evaluation Lean MVP](../../../../docs/roadmaps/AGENT_LAYER_HORIZON_3_LEAN_EVALUATION_MVP.md)
- [Horizon 3 Evaluation User Stories](../../../../docs/roadmaps/AGENT_LAYER_HORIZON_3_EVALUATION_USER_STORIES.md)
