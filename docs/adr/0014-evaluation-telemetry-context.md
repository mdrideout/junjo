# ADR 0014: Bounded evaluation telemetry context

- Status: Accepted
- Date: 2026-07-27
- Owners: Junjo platform and Python SDK

## Context

ADR 0013 makes Studio's Attempt record the canonical join between an
evaluation result and one semantic Junjo execution. That ledger is sufficient
for exact evidence lookup, but it does not make evaluation-generated traces
visibly distinct from ordinary application traffic while inspecting raw
telemetry.

Evaluation context must not replace the Attempt binding, change the
application's OpenTelemetry service identity, or copy dataset metadata onto
every Node, model, Tool, Store, and provider span. Doing so would increase
telemetry size and ingestion work in the low-resource Studio profile.

The current OpenTelemetry GenAI semantic conventions do not define a stable,
complete contract for Junjo's dataset, run, case, Attempt, and execution-role
identities. Junjo therefore needs a small governed extension that can later
adopt compatible standard attributes without silently changing meaning.

## Decision

### Context is immutable and run-local

The Python SDK owns one immutable `EvaluationContext` for each evaluation
Attempt or generated-case execution. It is created from Studio's canonical
identities and the clean application source revision. Applications do not
construct telemetry dictionaries or mutate active context.

The context has these logical fields:

- context version;
- run class;
- Dataset ID;
- Run ID when a Run exists;
- Case ID or pre-creation Case key;
- Attempt ID when an Attempt exists;
- clean source revision; and
- execution role.

Run class is one of `dataset_generation` or `evaluation`. Ordinary application
execution does not create an evaluation context; absence is its only
representation.

Execution role is one of `orchestrator`, `subject`, `judge`, or `verifier`.

### Junjo uses bounded role spans

For an evaluation Attempt, the SDK creates one
`junjo.evaluation.attempt` orchestration span. The real Node, Workflow, or
Agent runs beneath one `junjo.evaluation.subject` role span. Evaluation logic
runs beneath `junjo.evaluation.judge` and, when explicitly requested, verifier
role spans.

Generated-case execution uses one `junjo.evaluation.dataset_generation`
orchestration span plus the same bounded subject role span. It does not invent
a Run or Attempt identity before those records exist.

The context attributes appear on these Junjo-owned orchestration and role
spans only:

- `junjo.evaluation.context.version`;
- `junjo.evaluation.run_class`;
- `junjo.evaluation.dataset.id`;
- `junjo.evaluation.run.id`, when present;
- `junjo.evaluation.case.id`, when present;
- `junjo.evaluation.case.key`, before a generated Case has an ID;
- `junjo.evaluation.attempt.id`, when present;
- `junjo.evaluation.source.revision`; and
- `junjo.evaluation.role`.

Every Junjo-owned evaluation span also carries the active
`junjo.telemetry.contract_version`. Role spans use ordinary OpenTelemetry
parentage and status/error conventions. They are not Junjo executables and do
not receive fake executable definition or runtime IDs.

### Application and evidence identity stay truthful

The application's configured `service.namespace`, `service.name`, and optional
`service.version` remain unchanged. The subject's real Workflow or Agent
runtime ID is still emitted by its normal public lifecycle. A Node target uses
the truthful generated one-Node Workflow accepted by ADR 0010.

The Studio Attempt-to-evidence binding remains authoritative membership.
Native targets bind the semantic Junjo execution identity. An external target
accepted by ADR 0015 binds the exact standard OpenTelemetry span that
represents its subject. Evaluation attributes make traces classifiable and
readable; Studio does not infer result membership from them and does not copy
them into per-span relational rows.

External target spans remain ordinary descendants of the bounded subject role
span. Evaluation context is not copied onto those descendants, and they do not
receive fabricated Junjo executable identity.

### Contract version 2 remains active

This is an optional governed extension of telemetry contract version 2.
Existing version 2 evidence remains valid without evaluation spans, and no
existing executable, operation, Store, payload, or service-identity semantics
change.

SDK producer tests must prove exact attribute presence, omission, parentage,
and application service identity for evaluation and generated-case execution.
Studio consumer validation must prove that the additional non-executable spans
remain available as trace evidence without being mistaken for Workflow,
Subflow, Node, RunConcurrent, or Agent owners.

## Consequences

- Evaluation and dataset-generation traffic is explicit in raw telemetry.
- One Attempt adds a small fixed number of spans and attributes rather than
  multiplying metadata across every descendant.
- Studio ingestion, authorization, WAL, Parquet, hot/cold query, and memory
  architecture do not change.
- Dataset and candidate identity remains queryable from the evaluation ledger
  even if sampling removes an orchestration span.
- A future OpenTelemetry evaluation convention can be adopted through an
  explicit contract decision after its semantics are stable and equivalent.

## Rejected alternatives

- Put evaluation metadata on every descendant span: bounded parentage already
  supplies context and repeated attributes increase storage and ingestion
  work.
- Replace the application's service name with an eval-only service: this makes
  application identity untruthful and breaks semantic execution resolution.
- Use `ExecutionCorrelation` for Dataset or Attempt identity: application
  domain correlation and evaluation control membership have different owners.
- Infer Attempt membership only from telemetry attributes: result writes and
  telemetry readiness have independent failure modes.
- Add evaluation columns to Studio's span metadata index: the MVP already has
  an exact indexed Attempt binding and does not need per-span duplication.

## Related decisions

- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
- [ADR 0007: Application execution correlation and Studio resolution](0007-execution-correlation-and-studio-resolution.md)
- [ADR 0010: Node Evaluation Execution](0010-node-evaluation-execution.md)
- [ADR 0013: SDK-orchestrated, application-executed Studio evaluations](0013-application-executed-studio-evaluations.md)
- [Studio ADR 010: Evaluation control persistence and API](../../apps/studio/docs/adr/010-evaluation-control-persistence-and-api.md)
- [ADR 0015: Optional external Agent framework integrations](0015-optional-agent-framework-integrations.md)
