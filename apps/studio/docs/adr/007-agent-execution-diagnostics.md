# ADR-007: Agent execution diagnostics

## Status

Accepted

## Date

2026-07-13

## Context

Junjo AI Studio currently interprets Graph-based Workflow telemetry. Its
backend has Workflow-oriented query behavior, and its frontend matches spans to
serialized Graph nodes. An Agent instead produces a dynamic sequence of model
and Tool operations, sometimes containing nested Workflows.

Studio must provide complete Agent diagnostics without fabricating a Graph,
moving product semantics into ingestion, exposing physical telemetry storage to
the frontend, or creating a second copy of the shared telemetry contract.

Root ADR 0006 defines telemetry contract version 2, canonical Agent fixtures,
operation ordering, Store revisions, payload modes, and SDK/Studio conformance.
This ADR owns how Studio preserves, queries, and presents that evidence.

## Decision

### Studio is the Agent evidence plane

Studio provides a semantic diagnostic path from ingested OpenTelemetry evidence
to an Agent execution view:

`OTLP ingestion -> durable span storage -> semantic Agent query -> diagnostic UI`

Each layer has one responsibility:

- ingestion preserves shared-contract fields and parentage;
- the backend interprets stored evidence into typed Agent query results;
- the frontend presents those semantic results and interactive state history.

Studio does not control Agent execution, evaluate model quality, or modify
Agent definitions in the initial diagnostic feature.

### Ingestion remains transport and durable storage

The Rust ingestion service preserves every Agent-contract attribute, event,
status, parent relationship, complete resource-attribute object, and OTLP
dropped-evidence counter defined by ADR 0006. Span records retain dropped
attribute, event, and link counts; event records retain their dropped-attribute
count; normalized resource evidence retains its dropped-attribute count.

Ingestion does not:

- parse Agent definitions or normalized model payloads;
- reconstruct Agent state;
- apply payload redaction;
- classify Agent outcomes;
- create Agent-specific storage;
- depend on the backend being available;
- own Agent indexing or query policy.

This is a preservation guarantee for the shared Agent contract, not a claim
that the ingestion pipeline preserves every possible OTLP field. Ingestion
preserves loss signals but does not decide what they mean.

File-level Agent selection metadata analogous to existing Workflow file
metadata may be added if list-query performance requires it. The initial design
does not add a per-Agent semantic database or a second ingestion path.

### Backend owns semantic interpretation

The backend adds a dedicated Agent diagnostics feature with typed summary and
detail contracts.

An `AgentExecutionSummary` contains:

- trace and Agent span identity;
- normalized service namespace, service name, and optional service version;
- Agent key, display name, and structural ID;
- start, end, and duration;
- completed, failed, or cancelled outcome;
- termination reason;
- model-request count plus requested, admitted, started, and completed Tool-call
  counts;
- normalized usage summary.

The list query is scoped by `(service.namespace or "", service.name)` and
supports filters for Agent key, structural ID, service version, outcome, and
time range. Physical Parquet, DataFusion, and SQLite selection remain behind
backend repository and service boundaries.

An `AgentExecutionDetail` is addressed by trace ID and Agent span ID. It
contains:

- the summary;
- definition and capabilities;
- validated input and output when present, or rejected boundary candidates and
  validation diagnostics;
- ordered model and Tool operations;
- Store start, end, revisions, transitions, and reconstruction status;
- owning errors or cancellation;
- nested Workflow references;
- contract-evidence integrity status, diagnostic reasons, OTLP loss counters,
  and payload modes.

Integrity status is `complete` or `partial` for the supported contract. It is
`complete` only when required slots and terminal facts exist, owner counts
reconcile with contiguous operation and transition sequences, Store replay is
verified when reconstructable is claimed, and all preserved contract-relevant
drop counters are zero. `partial` includes stable diagnostic reason codes. This
status covers Junjo contract evidence, not arbitrary provider child spans.

The backend:

- validates the active telemetry contract;
- selects the Agent span and walks descendants only to discover boundaries;
- selects model and Tool operations only when `junjo.agent.runtime_id` equals
  the detail Agent's `junjo.executable_runtime_id`, then orders that owner set
  by `junjo.agent.operation.sequence`;
- selects Store events only when `junjo.store.id` equals the detail Agent's
  `junjo.agent.store.id`, then orders that owner set by
  `junjo.store.transition.sequence`;
- stops semantic assembly at nested executable spans and exposes typed Workflow
  or Agent references instead of merging their independent operations or Store
  events into the parent;
- reconciles operation and transition counts and validates unique contiguous
  sequences, revision continuity, terminal revision, and patch replay;
- treats the backend result as authoritative for Store reconstructability and
  contract-evidence integrity;
- interprets preserved dropped-evidence counters without asking ingestion to
  classify them;
- preserves explicit full, redacted, excluded, and reference payload modes;
- distinguishes absent evidence caused by failure from policy-transformed
  evidence;
- returns typed semantic data rather than storage-shaped rows.

Timestamps remain available for display and duration. They are not used to
resolve operation or state ordering.

The existing raw trace API remains useful as a secondary diagnostic surface,
but raw storage-shaped evidence is not embedded in `AgentExecutionDetail`. A
secondary raw panel fetches the raw trace separately using identities from the
semantic detail. The Agent frontend does not infer product behavior by scanning
those rows.

### Frontend renders realized execution, not a Graph

Studio adds an Agent execution feature with its own typed API schema and
feature state. The primary view contains:

- Agent identity, structural ID, outcome, and termination reason;
- limits, counts, usage, and duration;
- definition, instructions, input/output schemas, and available Tools;
- application input and final output;
- a chronological model and Tool timeline/tree;
- normalized model requests, returned response candidates, and validated
  responses;
- requested and validated Tool arguments, returned result candidates, and
  validated results;
- state revisions with before, after, patch, and full-state views;
- failure or cancellation at the operation that owns it;
- nested Workflow navigation.

The Agent timeline is not rendered through Mermaid and has no static Graph
snapshot. A nested Workflow links to the existing Workflow detail and Graph
view using its actual trace and span identity.

Missing, redacted, excluded, referenced, and genuinely empty evidence are
visually distinct. Studio does not infer hidden content or automatically fetch
opaque references.

Raw attributes and events may remain available in a secondary panel for
low-level diagnosis. They are not the primary product model.

### Store reconstruction is one backend semantic capability

Workflow and Agent diagnostics both require ordered Store history. The backend
owns one generic Store reconstruction and integrity utility that:

- groups events by Store ID;
- uses revision and transition sequence as authoritative order;
- applies RFC 6902 patch arrays;
- detects gaps, conflicts, and non-reconstructable payload modes;
- verifies that applying every available patch exactly produces the emitted end
  state before reporting a timeline as reconstructable;
- produces typed before, after, patch, and detailed state projections plus
  diagnostic reason codes.

Feature selection and presentation remain separate:

- Workflow backend services select Workflow evidence;
- Agent backend services select Agent evidence;
- the shared backend utility performs only Store reconstruction and integrity
  verification.

The frontend may apply already verified patches for interactive navigation, but
it consumes the backend's reconstructability and integrity result. It does not
publish a competing semantic verdict. Frontend projection tests are generated
from canonical backend results.

### Active contract support is strict

Studio supports the active telemetry contract version 2 when the Agent runtime
lands. Unsupported or malformed Agent evidence is explicitly rejected or
labelled unsupported. There is no compatibility parser, guessed fallback, or
silent coercion.

The contract version, schemas, fixtures, SDK producer, ingestion preservation,
backend interpretation, and frontend consumer change atomically as required by
ADR 0006. After that merge, Studio version 2 is deployed before the SDK is
published; Studio immediately rejects version 1 semantic evidence. No dual
parser or cutover fallback is introduced.

## Boundaries

- Root ADR 0006 and `contracts/telemetry` own emitted names, payload schemas,
  canonical fixtures, and conformance semantics.
- SDKs own execution and emission.
- Ingestion owns transport conversion and durable preservation.
- Backend repositories own physical selection; Agent services own semantic
  assembly.
- Frontend schemas own API validation; feature code owns presentation and
  interaction.
- Studio never imports SDK runtime internals.
- Public hooks are not an ingestion or telemetry path.

## Validation

Canonical Agent fixtures must prove:

- Agent-contract fields and events survive ingestion;
- summary filtering finds standalone and Workflow-nested Agents;
- detail queries either assemble all required Agent contract evidence or return
  `partial` with stable reasons;
- boundary input/history rejection renders with no fabricated Store or
  operations;
- operation sequence overrides timestamp ordering;
- owner runtime and Store IDs prevent nested Agent operation and transition
  sequences from contaminating their parent detail;
- counts, ordinals, call IDs, and limits satisfy ADR 0006 invariants;
- Store transition sequence and revisions reconstruct the expected state only
  when integrity verification succeeds;
- every consumer-only invalid derivative for malformed or incomplete operation
  and Store sequences is rejected with its declared diagnostic;
- nested Workflows retain Graph matching and navigation;
- unknown Tools fail without a fabricated Tool span;
- malformed model responses and Tool-output validation show returned candidates
  separately from validated values;
- model and Tool failures appear on the owning operation;
- non-terminal hook failure remains diagnostic while the Agent completes;
- terminal observer-delivery cancellation remains observer evidence without
  rewriting the committed Agent outcome;
- cancellation remains distinct from failure;
- payload modes remain distinct from empty values;
- resource service scope and version remain queryable across releases;
- dropped-evidence counters survive ingestion and force partial integrity;
- frontend schemas and views accept every supported scenario.

Valid producer and consumer span fixtures directly drive ingestion and backend
semantic assembly. Frontend tests consume the typed backend projections
generated from those fixtures through an integration adapter, not a frontend
raw-span interpreter or copied Studio fixture. SDK producer equivalence applies
only to the producer fixture set. Cross-component validation runs before the
version 2 contract can merge.

## Consequences

Developers can diagnose dynamic Agent behavior with the same transparency as
Workflows while seeing the execution model truthfully. The backend provides a
stable semantic API, and the frontend no longer has to infer Agent behavior
from physical span rows.

Studio gains a new feature module and shared backend Store reconstruction
utility.
Evidence-heavy traces may be large, and strict active-version validation means
SDK and Studio releases must remain coordinated during greenfield development.

## Rejected Alternatives

- Render Agent as a static Graph: its path is realized at runtime.
- Add Agent semantics to ingestion: transport storage should not own product
  interpretation.
- Let the frontend scan raw spans: physical storage would become a product API.
- Copy nested Workflow evidence into Tool payloads: it duplicates the Graph
  source of truth.
- Infer ordering from timestamps: sequence and revision fields are
  authoritative.
- Treat missing and redacted as empty: it hides evidence quality.
- Add compatibility fallback for version 1: Agent semantics do not exist in
  that contract.
- Build an Agent-specific state diff engine: Store reconstruction is a shared
  concern.

## Deferred Decisions

- autonomous Agent access to Studio evidence;
- failure cohorts, evaluation datasets, experiments, and replay;
- retention, privacy, and access-control product policy;
- automatic reference resolution;
- live streaming visualization;
- multi-agent and handoff views;
- generated diagnostics interfaces;
- automated promotion or source modification.

## Related Decisions

- [Root ADR 0006: Agent telemetry contract](../../../../docs/adr/0006-agent-telemetry-contract.md)
- [Root ADR 0005: Agent and Workflow composition](../../../../docs/adr/0005-agent-workflow-composition.md)
- [ADR-004: Events JSON contract](004-events-json-contract.md)
- [ADR-005: Studio frontend interaction foundation](005-studio-frontend-interaction-foundation.md)
