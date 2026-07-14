# ADR 0006: Agent telemetry contract

- Status: Accepted
- Date: 2026-07-13
- Last clarified: 2026-07-14
- Owners: Junjo platform

## Context

Junjo telemetry contract version 1 describes Graph-based Workflow execution.
It has no Agent executable, model or Tool operation semantics, stable Agent key,
operation ordering, or Store revisions. Current Store events are ordered only
by timestamps and may encode an empty JSON Patch as `{}`, which is not an RFC
6902 patch array.

An Agent run is a dynamic trace. Studio must be able to determine what Agent
ran, what definition it used, what normalized requests and responses crossed
the ModelDriver boundary, which Tools were requested, what each Tool received
and returned, how state changed, and why execution ended.

This evidence is a shared platform contract. It cannot be an SDK-internal
object model or Studio inference over arbitrary spans.

## Decision

### Agent telemetry is contract version 2

Agent semantics and generic Store revision semantics are a breaking telemetry
contract change. The first Horizon 1 implementation must atomically:

1. increment `contracts/telemetry/VERSION` from 1 to 2;
2. update the normalized fixture schema and add Agent payload schemas;
3. update every canonical Workflow fixture for version 2 Store semantics;
4. update the Python SDK constant, Workflow producer, and Agent producer tests;
5. preserve normalized service resource identity and OTLP evidence-loss counters;
6. update Studio ingestion, backend, and frontend consumers;
7. validate canonical producer and consumer conformance in the same change.

The accepted sequencing did not bump the active contract before those producers
and consumers existed. The atomic Horizon 1 implementation now makes contract
version 2 the truthful active source contract.

During greenfield development, SDK and Studio support only the active contract
version. No compatibility fallback or dual-emission path is added.

Every Junjo-owned semantic executable or operation span carries
`junjo.telemetry.contract_version = 2`.

### Executables and operations remain distinct

The Agent run is a Junjo executable:

- `junjo.span_type = "agent"`.

Model requests and Tool calls are operations inside that executable. They do
not receive `junjo.span_type` and are not assigned fake definition, Graph, or
Store identity. They use:

- `junjo.agent.operation_type = "model_request"`; or
- `junjo.agent.operation_type = "tool"`.

Every operation span also carries:

- `junjo.agent.key`;
- `junjo.agent.runtime_id`;
- `junjo.agent.operation.sequence`.

`junjo.agent.runtime_id` is the same value as the public Agent `run_id` and the
owning Agent span's `junjo.executable_runtime_id`. It links operations to their
owner; it does not introduce another identity.

`junjo.agent.operation.sequence` is a contiguous 1-based sequence assigned
across all emitted model and Tool operation spans in one Agent run. The owning
Agent span records `junjo.agent.operation.count`; observed sequences must be
exactly `1..count`. Studio uses this as the authoritative operation order and
detects missing operation evidence. Timestamps are display and duration data,
not a total-order mechanism.

Provider instrumentation may create additional child spans, but Junjo and
Studio do not depend on provider-specific spans for Agent semantics.

### Runtime parentage is the execution hierarchy

Standalone Agent execution has this hierarchy:

`Agent -> model and Tool operation spans`

A Workflow invoked by a Tool retains its normal Graph evidence:

`Agent -> Tool operation -> Workflow -> Nodes`

An Agent invoked by a Workflow Node remains a dynamic child executable:

`Workflow -> Node -> Agent -> model and Tool operations`

An Agent never emits a Workflow execution Graph snapshot. A nested Workflow
never has its Graph copied into Agent or Tool attributes.

### Agent identity is queryable across releases

The Agent span uses existing generic executable attributes:

- `junjo.executable_definition_id` for one in-process Agent definition object;
- `junjo.executable_runtime_id` for one Agent run;
- `junjo.executable_structural_id` for the deterministic Agent fingerprint;
- `junjo.parent_executable_definition_id`,
  `junjo.parent_executable_runtime_id`, and
  `junjo.parent_executable_structural_id` when a semantic parent executable
  exists; and
- `junjo.parent_executable_type` alongside those parent identity fields, with
  exactly one of `workflow`, `subflow`, `node`, `run_concurrent`, or `agent`.

The four parent fields form one all-or-none semantic reference and must match
the referenced executable span. Physical OpenTelemetry parentage may include a
Tool operation between an Agent and a nested Workflow; the semantic parent in
that case is still the owning Agent. The type field is required for truthful
cross-domain navigation and is not inferred from identifier formats.

Physical OpenTelemetry parentage alone does not create a semantic executable
parent. For example, an Agent started inside an HTTP server span retains that
physical `parent_span_id` but emits none of the four
`junjo.parent_executable_*` fields unless a Junjo executable is active.

It also carries:

- `junjo.agent.key` for the application-owned logical identity;
- `junjo.agent.name` for the display name;
- `junjo.agent.runtime_id`, equal to `junjo.executable_runtime_id`, so the owner
  and operation spans share one query key.

Logical Agent identity is scoped by the normalized OpenTelemetry resource pair
`(service.namespace or "", service.name)`. Optional `service.version`
identifies a deployed release when supplied but is not part of the logical key.
Canonical fixtures cover populated and absent optional resource fields, and
Studio list queries require the service scope rather than treating Agent keys
as globally unique.

It does not carry `junjo.enclosing_graph_structural_id` unless the span itself
is a Graph executable. Being nested under a Node does not make an Agent part of
that Graph.

### Structural identity is canonical and pre-policy

Agent structural material is one JSON object with this exact version 1 shape:

```json
{
  "v": 1,
  "agentKey": "chat",
  "instructions": "...",
  "inputSchema": {},
  "model": {
    "driverKey": "...",
    "provider": "...",
    "model": "...",
    "settings": {}
  },
  "tools": [
    {
      "name": "...",
      "description": "...",
      "inputSchema": {},
      "outputSchema": {}
    }
  ],
  "outputSchema": {},
  "limits": {
    "modelRequests": 1,
    "toolCalls": 1
  }
}
```

Tool order is significant. JSON object member order is not.

It excludes:

- generated definition and run IDs;
- display-only Agent name;
- Hooks and callback identity;
- Python callable, class, module, or memory identity;
- application dependencies;
- telemetry payload policy;
- credentials and mutable provider clients.

Tool structural material has this exact version 1 shape:

```json
{
  "v": 1,
  "name": "...",
  "description": "...",
  "inputSchema": {},
  "outputSchema": {}
}
```

`contracts/telemetry/schemas/agent-structural-material.v1.schema.json` and
`tool-structural-material.v1.schema.json` are the normative shape owners when
version 2 lands. A validated instance is canonicalized with RFC 8785, encoded
as UTF-8, and hashed with SHA-256.

Structural material is restricted to the RFC 8785 I-JSON input domain.
Construction and conformance validation reject duplicate object names,
non-finite or non-binary64 numeric values, integers outside the interoperable
safe-integer range, and strings containing lone Unicode surrogates. Unicode is
preserved without normalization. Fingerprint fixtures cover safe numeric
boundaries, exponent and negative-zero serialization, and canonically distinct
composed and decomposed Unicode.

ADR 0004 applies that portable value domain to every normalized Agent JSON
boundary. Contract version 2 telemetry producers and consumers enforce the
same rule for every Agent and Workflow payload—including Store start, candidate
state, transition patch, and end state—and for normalized usage, counts,
limits, identifiers, and text rather than only for structural material. Store
validation occurs before tracker mutation or live-state commit so telemetry
portability failure cannot leave a committed state without its required
transition evidence. A producer must reject a nonportable value before
emission. A consumer that receives nonportable or duplicate-name JSON reports
typed partial or invalid evidence; it never repairs the value, silently drops
one attribute while retaining `mode=full`, or raises an untyped server error.

Decoded contract JSON has a maximum nesting depth of 128. Producers reject a
deeper value at the boundary, and consumers report
`payload_nesting_too_deep` without recursively walking until the process
stack fails. The same bound applies to Agent, Workflow, and Store payload
slots; it is a transport-safety limit, not an application-state model.

The JSON Schemas embedded in structural material and normalized requests use
ADR 0004's generated-schema profile: presentation `title` annotations are
removed; set-valued `required`, `dependentRequired`, array-valued `type`, and
`enum` members are canonicalized; object schemas with declared `properties`
are closed with `additionalProperties: false`, while explicitly open
structured objects are rejected; property-less dictionary schemas may retain
an explicit boolean or schema-valued `additionalProperties`; reachable local
definitions are deterministically renamed under `$defs`; local references and
discriminator mappings are rewritten; and unreachable definitions are
omitted. Contract fingerprint vectors include renamed nested definitions,
recursive definitions, discriminator mappings, closed structured objects, an
explicit open dictionary, an application property named `title`, field-order
and object-order variations. SDK and Studio fingerprint implementations must
compare the resulting structural IDs exactly; conformance tests may not
normalize those IDs away.

The emitted Agent structural ID is
`agent_sha256:<64 lowercase hexadecimal characters>`. Tool structural material
uses the same algorithm and is emitted as
`tool_sha256:<64 lowercase hexadecimal characters>`.

Structural IDs describe declared configuration, not deployed source bytes.
OpenTelemetry resource attributes such as service name and service version
remain responsible for deployment identity.

Fingerprinting happens before telemetry payload transformation. A redacted,
excluded, or referenced definition snapshot cannot change structural identity.
A canonical language-independent fingerprint fixture proves identical output
across SDK implementations.

The canonical structural-material object is fingerprint input, not a required
unredacted telemetry payload. The producer emits the structural ID. Any
diagnostic definition snapshot remains governed by the payload slot contract
below.

The version 2 contract also adds normative schemas for Agent definition
snapshots, normalized model requests and responses, per-response usage, and
aggregate usage. JSON Schema files, not language-native classes or examples in
this ADR, own exact serialized property names.

### Payload transformation is explicit

The producer applies one payload policy at the semantic serialization boundary.
The Horizon 1 Python producer uses the built-in full-evidence policy
`junjo.full.v1` for both Workflow and Agent telemetry. Custom policy selection
is deferred, but the language-independent contract defines every mode now so
Studio does not infer content from absence. Every JSON-valued OpenTelemetry
attribute is encoded as a JSON string; portable contract behavior never relies
on an OpenTelemetry map attribute.

Every semantic payload value owns a payload slot rooted at attribute `P`. A
present slot always requires adjacent metadata:

- `P.mode`: `full`, `redacted`, `excluded`, or `reference`;
- `P.policy`: a stable policy key.

The version 2 schemas enforce the slot with a conditional `oneOf`:

- `full` or `redacted`: `P` is a required JSON string and `P.reference` is
  absent;
- `reference`: `P.reference` is a required opaque application-owned reference
  and `P` is absent;
- `excluded`: both content and reference are absent.

`P.mode` and `P.policy` remain required in every case. Missing content is never
interpreted as an empty value. Later sections say a span "has a payload slot"
when this metadata is required; the base `P` content remains conditional on
the slot mode.

Payload policy governs only:

- Agent definition snapshot, rejected input/history candidates, validated input,
  output, and state start/end;
- normalized model request, response candidate, and validated response;
- Tool requested arguments, validated arguments, result candidate, and
  validated result;
- state JSON patches.

Identity, structural IDs, limits, counts, outcome, termination reason, and
normalized usage are contract metadata and are not transformed by payload
policy.

One deterministic state projection belongs to one stable policy key. A
producer applies the same serializer and projection to Store start, every
committed revision, and Store end, then computes patches between those
projected states. It never independently transforms a live-state patch.
Workflow and Agent state slots and patches use the same slot rules; the Horizon
1 producer emits all of them as `full` with policy `junjo.full.v1`.

Studio displays the mode and does not automatically resolve references. The
contract requires no original-content digest. Payload policy never changes live
Agent state, Tool input, Tool result, or the structural fingerprint.

No runtime layer silently truncates payloads. A size policy must explicitly
redact, exclude, or reference the value. Large binary content is represented by
application-owned metadata or references and is not embedded in span
attributes.

“Exact normalized payload” means the exact JSON value after declared
application, ModelDriver, Tool, and Pydantic serialization boundaries. It does
not mean arbitrary Python object memory or a provider's private wire format.

Diagnostics do not require or fabricate hidden chain-of-thought. An explicit
provider reasoning summary returned as ordinary response content is a normal
payload subject to the selected policy.

### Agent span contract

Every Agent span requires these scalar attributes and payload slots. For a
payload slot, the base content or reference is conditional as defined above:

| Concern | Required attributes |
| --- | --- |
| Contract | `junjo.telemetry.contract_version`, `junjo.span_type` |
| Identity | `junjo.executable_definition_id`, `junjo.executable_runtime_id`, `junjo.executable_structural_id`, `junjo.agent.key`, `junjo.agent.name`, `junjo.agent.runtime_id` |
| Definition | payload slot rooted at `junjo.agent.definition_snapshot` |
| State availability | `junjo.agent.state.available` |
| Limits | `junjo.agent.limit.model_requests`, `junjo.agent.limit.tool_calls` |
| Counts | `junjo.agent.operation.count`, `junjo.agent.model_request.count`, `junjo.agent.tool_call.requested_count`, `junjo.agent.tool_call.admitted_count`, `junjo.agent.tool_call.started_count`, `junjo.agent.tool_call.completed_count` |
| Usage | `junjo.agent.usage` |
| Terminal state | `junjo.agent.outcome`, `junjo.agent.termination_reason` |

When `junjo.agent.state.available = true`, the span also requires:

- `junjo.agent.store.id`;
- payload slots rooted at `junjo.agent.input`, `junjo.agent.state.start`, and
  `junjo.agent.state.end`;
- `junjo.store.revision.start`;
- `junjo.store.revision.end`;
- `junjo.store.transition.count`;
- `junjo.store.reconstructable`.

The payload slot rooted at `junjo.agent.output` is present only after
successful output validation. A boundary input or history validation failure has
`junjo.agent.state.available = false` and does not fabricate Store or state
payloads.

For boundary rejection, the Agent span records
`junjo.agent.input_candidate.available` or
`junjo.agent.history_candidate.available` for the rejected boundary. When a
candidate is safely JSON-serializable, availability is true and the
corresponding payload slot is required. Otherwise availability is false and
the adjacent unavailable reason is `not_json_serializable`. Candidate evidence
is diagnostic only and never enters Agent state.

Candidate and validated payloads are independently meaningful. A candidate is
the portable value returned to a normalization boundary; a validated payload
is the detached value after declared schema validation and normalization,
including defaults. Therefore both slots obey their own schemas and transport
conditions, but the contract does not require their JSON values to be equal.

The owner conditional matrix is normative:

| Condition | Required evidence | Forbidden evidence |
| --- | --- | --- |
| `outcome = completed` | `termination_reason = final_output`, exactly one owner-scoped model response typed `final_output`, and the Agent output payload slot | failure or cancellation terminal transport |
| `outcome = failed` | any allowed non-success, non-cancellation termination reason and matching error/exception transport | Agent output payload slot |
| `outcome = cancelled` | `termination_reason = cancelled` and cancellation transport | error transport and Agent output payload slot |
| `state.available = false` | boundary input/history rejection, or `internal_error` with `AgentAdmissionError`; zero operation and Tool counts; empty aggregate usage | input, Store identity, Store revisions, Store transitions, state start/end, and operation activity |
| boundary input/history rejection | exactly the corresponding input or history candidate availability fact and conditional candidate slot | the other boundary candidate and all state/Store evidence |
| requested Tool count above the effective Tool limit | `limit_exceeded` with exceeded kind `tool_calls` | any other terminal reason |

`state.available = true` does not promise successful completion; it means the
Store boundary was admitted and its available evidence must satisfy the Store
contract. Owner output is present if and only if completion succeeded.

`junjo.agent.model_request.count` is the number of ModelDriver operations
started. Tool-call counts mean:

- `requested_count`: normalized calls returned by models;
- `admitted_count`: calls in batches that passed budget, resolution, and
  argument validation;
- `started_count`: Tool service invocations begun;
- `completed_count`: Tool outputs successfully validated and committed.

Requested count may exceed the effective limit only for the rejected
over-budget batch. A preflight diagnostic Tool span does not increment started
count.

Owner-span count invariants are normative:

- all counts are non-negative integers;
- `junjo.agent.operation.count` equals the number of operation spans whose
  `junjo.agent.runtime_id` equals the owner runtime ID, and their operation
  sequences are exactly `1..junjo.agent.operation.count`;
- `junjo.agent.model_request.count` equals the number of owner-scoped model
  operation spans, whose model ordinals are exactly
  `1..junjo.agent.model_request.count`;
- `junjo.agent.tool_call.requested_count` equals the number of calls across validated
  current-run `ToolCallsResponse` values; their call IDs are unique and their
  derived run-global ordinals are exactly
  `1..junjo.agent.tool_call.requested_count`;
- every Tool operation span matches one requested call by both call ID and
  ordinal, and no requested call owns more than one Tool span;
- an emitted Tool span represents either one admitted call or the single
  declared-Tool argument failure permitted by batch preflight; unknown and
  over-budget calls have no Tool span;
- after removing their common `junjo.agent.tool_call` prefix, the four Tool
  counters obey
  `completed_count <= started_count <= admitted_count <= requested_count`;
- `junjo.agent.model_request.count <= junjo.agent.limit.model_requests` and
  `junjo.agent.tool_call.admitted_count <= junjo.agent.limit.tool_calls`;
- `junjo.agent.tool_call.requested_count > junjo.agent.limit.tool_calls` is
  valid only for a terminal
  `limit_exceeded` outcome with exceeded kind `tool_calls`, and model-budget
  exhaustion occurs with exceeded kind `model_requests` and
  `junjo.agent.model_request.count == junjo.agent.limit.model_requests` before
  another model span starts.

Consequently, `junjo.agent.operation.count` is the model-operation count plus
the observed owner-scoped Tool-operation count; it is not the requested or
admitted Tool count.

`junjo.agent.model.usage` is a JSON string validated by
`model-usage.v1.schema.json` with this shape and any unsupported token fields
omitted:

```json
{
  "v": 1,
  "inputTokens": 10,
  "outputTokens": 4,
  "cachedInputTokens": 2,
  "reasoningTokens": 1,
  "totalTokens": 14
}
```

`junjo.agent.usage` is a JSON string validated by
`agent-usage.v1.schema.json`:

```json
{
  "v": 1,
  "modelResponses": 2,
  "fields": {
    "inputTokens": {"sum": 20, "observations": 2},
    "outputTokens": {"sum": 8, "observations": 2}
  }
}
```

The allowed field names are `inputTokens`, `outputTokens`,
`cachedInputTokens`, `reasoningTokens`, and `totalTokens`. A field is absent
when no response reports it. Observations distinguish an absent provider fact
from a reported zero and from an incomplete aggregate.
`modelResponses` counts every response that passes normalized response
validation, including responses with no usage object. Each field's
`observations` counts only validated responses that reported that field.

`junjo.agent.outcome` is one of:

- `completed`;
- `failed`;
- `cancelled`.

`junjo.agent.termination_reason` is the more specific stable reason:

- `final_output`;
- `input_validation_error`;
- `history_validation_error`;
- `limit_exceeded`;
- `model_error`;
- `model_response_error`;
- `unknown_tool`;
- `tool_input_validation_error`;
- `tool_error`;
- `tool_output_validation_error`;
- `output_validation_error`;
- `internal_error`;
- `cancelled`.

`internal_error` is reserved for unexpected Junjo-owned runtime machinery,
not ModelDriver, Tool, validation, or application failures. An
`AgentAdmissionError` uses it before Store availability is published; an
admitted `AgentInternalError` uses it with only the Store facts that were
successfully verified. If the one selected success, failure, or cancellation
terminal transaction itself cannot commit, the terminal-commit internal error
supersedes that selected outcome and records the superseded outcome for
diagnosis. Studio must not fabricate a coherent Store end state to hide that
partial evidence.

When termination reason is `limit_exceeded`, the Agent span also requires
`junjo.agent.limit.exceeded` (`model_requests` or `tool_calls`) and
`junjo.agent.limit.attempted_count`. Tool-batch rejection additionally requires
`junjo.agent.limit.requested_batch_size`. Attempted count is the next
model-request ordinal or the cumulative Tool-call admission count that the
whole batch would have produced. These values match the typed
`AgentLimitExceededError`; they are absent for other terminal reasons.

State, revisions, counts, usage, outcome, and termination are finalized on
success, failure, and cancellation whenever the relevant data exists.

### Definition snapshot contract

The payload slot rooted at `junjo.agent.definition_snapshot` represents a
schema-versioned JSON object containing:

- Agent key and display name;
- instructions;
- input schema;
- declared ModelDriver descriptor;
- ordered Tool names, descriptions, structural IDs, and schemas;
- final-output schema;
- effective limits;
- executable structural ID.

The snapshot is diagnostic evidence and is payload-policy subject. The
structural ID is computed from the separate pre-policy material defined above.

### Model operation contract

A model-request operation span requires:

- `junjo.agent.operation_type = "model_request"`;
- Agent key and runtime ID;
- global operation sequence;
- `junjo.agent.model_request.ordinal`;
- `junjo.agent.model_request.state_revision`;
- `junjo.agent.model.driver_key`;
- `junjo.agent.model.provider`;
- `junjo.agent.model.name`;
- the payload slot rooted at `junjo.agent.model.request`;
- `junjo.agent.model.response_candidate.available`;
- `junjo.agent.model.response_type` only after normalized response validation
  succeeds;
- the payload slot rooted at `junjo.agent.model.response` when a validated
  response exists;
- `junjo.agent.model.usage` when usage exists.

The request and response are the exact normalized ADR 0004 values, not provider
wire payloads. Response type is `final_output` or `tool_calls`.

The model-request ordinal is the contiguous 1-based count of started model
operations. `junjo.agent.model_request.state_revision` is the Store revision
from which the immutable normalized request was captured, after model-start
bookkeeping is committed and before the driver factory or invocation begins.

When the ModelDriver returns, Junjo attempts diagnostic JSON serialization
before normalized response validation. A safely serializable returned value
sets `response_candidate.available = true` and requires the payload slot rooted
at `junjo.agent.model.response_candidate`, even if response validation later
fails. Otherwise availability is false and
`junjo.agent.model.response_candidate.unavailable_reason` is exactly one of
`not_returned`, `cancelled`, or `not_json_serializable`. A driver exception uses
`not_returned`. A validated response remains distinct from its diagnostic
candidate and from a response slot whose payload mode is `excluded`.

The model-operation conditional matrix is normative:

- candidate availability true requires the candidate payload slot and forbids
  an unavailable reason;
- candidate availability false forbids every member of the candidate payload
  slot and requires exactly one allowed unavailable reason;
- the validated response payload slot is present if and only if
  `junjo.agent.model.response_type` is present;
- a completed model operation has a validated response and an available
  candidate; a failed or cancelled operation has neither validated response
  nor normalized usage;
- `cancelled` is the candidate unavailable reason if and only if the operation
  itself is cancelled before a candidate is available; and
- normalized operation usage can exist only with a validated response and,
  when both values are inspectable, matches that response's usage field.

These are occurrence, identity, and terminal correspondences. They do not
assert raw candidate JSON equals normalized response JSON.

### Tool operation contract

A Tool operation span requires:

- `junjo.agent.operation_type = "tool"`;
- Agent key and runtime ID;
- global operation sequence;
- `junjo.agent.tool_call.id`;
- `junjo.agent.tool_call.ordinal`;
- `junjo.agent.tool.name`;
- `junjo.agent.tool.structural_id`;
- `junjo.agent.tool.state_revision.before`;
- `junjo.agent.tool.state_revision.after` when result state is committed;
- the payload slot rooted at `junjo.agent.tool.requested_arguments`;
- the payload slot rooted at `junjo.agent.tool.arguments` after validation;
- `junjo.agent.tool.result_candidate.available`;
- the payload slot rooted at `junjo.agent.tool.result_candidate` when safely
  serializable;
- the payload slot rooted at `junjo.agent.tool.result` after result validation.

The Tool-call ordinal is the contiguous 1-based position across every
normalized Tool call requested during the Agent run, including calls later
rejected by budget, resolution, or batch preflight. Calls without a Tool span
still consume an ordinal in the normalized model response. The ordinal is
therefore distinct from operation sequence and admitted, started, or completed
counts.

`junjo.agent.tool.state_revision.before` is sampled when the Tool operation
span begins, before service-factory construction or invocation.
`junjo.agent.tool.state_revision.after` is the Store revision after the
validated Tool result and its state transition are committed; it is absent
when no result is committed.

A declared Tool argument-validation failure owns a Tool span but never calls
the service. An unknown Tool has no Tool definition to own a Tool span; its
requested call remains visible in the model response and Agent failure.

When a Tool service returns, Junjo attempts diagnostic JSON serialization
before output validation. A serializable value is recorded as
`result_candidate` even when declared output validation later fails. If safe
serialization is impossible, `result_candidate.available = false` and
`junjo.agent.tool.result_candidate.unavailable_reason` identifies
`not_json_serializable`. That absence is distinct from an available candidate
whose payload mode is `excluded`. `result` remains the detached validated
output only.

Whenever `result_candidate.available = false`, unavailable reason is exactly
one of `not_invoked`, `service_failed`, `cancelled`, or
`not_json_serializable`. A preflight validation or factory failure uses
`not_invoked`.

The Tool-operation conditional matrix is normative:

- candidate availability true requires the result-candidate payload slot and
  forbids an unavailable reason;
- candidate availability false forbids every member of that slot and requires
  exactly one allowed unavailable reason;
- a Tool is considered started when a candidate is available or its unavailable
  reason is not `not_invoked`; started evidence requires validated arguments;
- a Tool-input validation failure forbids validated arguments;
- the validated result payload slot is present if and only if
  `junjo.agent.tool.state_revision.after` is present;
- a completed Tool has validated arguments, an available candidate, a validated
  result, and the committed after-revision; failed or cancelled Tools have no
  validated result or after-revision; and
- `cancelled` is the candidate unavailable reason if and only if the operation
  itself is cancelled before a candidate is available.

Requested arguments correspond to the normalized requested call, while
validated arguments and results are independently schema-validated values.
Defaults or other declared normalization may make a validated value differ
from its diagnostic candidate.

Preflight examines calls in model order. Only the first declared Tool with
invalid arguments receives a preflight diagnostic Tool span and operation
sequence. Valid calls in that rejected batch receive no Tool spans, no service
factory is constructed, and started count remains unchanged.

A nested Workflow is represented by normal child spans rather than copied Tool
attributes.

### Generic Store transitions gain revisions

Contract version 2 extends every Junjo Store, including Workflow Stores.

Every Store-owning executable span records:

- its existing executable-specific Store ID;
- `junjo.store.revision.start`;
- `junjo.store.revision.end`;
- `junjo.store.transition.count`;
- `junjo.store.reconstructable`.

Workflow spans retain `junjo.workflow.store.id` and Agent spans use
`junjo.agent.store.id`. The generic revision, transition-count, and
reconstructability attributes have one meaning for both executable types.

Initial Store revision is 0. Every successfully validated `set_state` call
emits a `set_state` event with:

- existing event ID, Store name, Store ID, and action;
- `junjo.store.transition.sequence`;
- `junjo.store.revision.before`;
- `junjo.store.revision.after`;
- the payload slot rooted at `junjo.state_json_patch`.

Event ID, Store name, Store ID, and action are nonempty portable text. One
Store ID has one stable Store name for its full trace. A producer derives that
name from the Store definition, never from whichever executable or helper
happened to call the transition; the action continues to identify that caller.
The event ID and action are never synthesized by consumers from event order or
span identity.

Every successful transition requires the patch slot's `.mode` and `.policy`.
Only content or reference is conditional on mode. An absent slot is missing
contract evidence, not policy exclusion.

Transition sequence is contiguous and 1-based for every successfully validated
`set_state` event. The owning span's transition count is the final sequence;
observed sequences must be exactly `1..count`. Revision is 0-based and
increments by exactly one only when live validated state changes. A true no-op
keeps before and after revision equal. A committed live change hidden by
telemetry projection still increments revision.

Sequence and revisions are assigned while the Store lock is held. They, not
timestamps, define state-event order.

For every Store, the producer applies the same state serializer and
deterministic payload projection at start, every revision, and end, then
computes the patch between consecutive telemetry-visible projections. It never
computes a live-state patch and transforms that finished patch independently.
All state and patch slots for one Store use the same mode and policy key.

Version 2 makes existing Workflow state start and end attributes into payload
slots and adds payload metadata to their Store patches. The Horizon 1 Workflow
producer uses `full` and `junjo.full.v1`, matching the Agent producer. This is a
telemetry contract change, not a Workflow runtime-policy API.

When patch content is present, `junjo.state_json_patch` is always an RFC 6902
JSON array string. A transition with no telemetry-visible change uses `[]`,
never `{}`.

`junjo.store.reconstructable` is a verified integrity fact, not a payload-mode
inference. It is true only when:

- state start and end content are present;
- the same serializer, mode, and policy key govern start, end, and every patch;
- observed transition sequences are exactly `1..transition.count`;
- the first revision-before equals `revision.start`, every revision-before
  equals the previous revision-after, and each revision-after is equal to or
  exactly one greater than revision-before;
- the final revision-after, or start when there are no transitions, equals
  `revision.end`;
- every transition has a valid RFC 6902 patch array, including `[]` for a
  telemetry-visible no-op;
- applying every patch in sequence produces exactly the emitted end state.

Full mode normally qualifies. Redacted mode qualifies only when the policy
produces one coherent state projection and verification succeeds. Excluded and
reference modes are false without producer-supplied content; Studio does not
resolve references implicitly. The SDK sets this flag after terminal
verification, and Studio independently verifies it while consuming evidence.

Revisions and transition sequence remain available even when state content is
not reconstructable.

The generic owner-span facts let Studio detect a missing trailing event,
including a missing no-op whose revision would not have changed. Workflow owner
spans retain their existing Workflow state, Store, and Graph attributes; only
the shared telemetry evidence contract changes.

Each state event is attached to the causal active span. Model-operation
bookkeeping and response commits belong to the model span; Tool start and
result commits belong to the Tool span; run admission, rejected-batch, and
terminal commits without a narrower operation owner belong to the Agent span.
The allowed action correspondence is exact: model spans own
`record_model_start` and `record_model_response`; Tool spans own
`record_tool_started` and `record_tool_result`; and the Agent owner span owns
`admit_tool_batch`, `commit_success`, and `set_terminal_reason`. A matching
Store event attached to any other span is out-of-scope evidence and is not
replayed.

### Contract evidence loss is observable

Version 2 normalized span fixtures add the complete OpenTelemetry resource
attribute object and its `resource_dropped_attributes_count`, plus non-negative
span `dropped_attributes_count`, `dropped_events_count`, and
`dropped_links_count` fields. Every normalized span event also preserves its
OTLP `dropped_attributes_count` as `droppedAttributesCount` in the canonical
event JSON shape owned by Studio ADR 004. SDK producer fixtures use zero unless
a loss scenario is intentional; ingestion must preserve the values without
interpreting them.

The canonical event timestamp `timeUnixNano` is an exact unsigned 64-bit
decimal string, not a JSON number. This preserves the full OTLP nanosecond
domain across Rust, Python, JSON, and TypeScript. Its lexical form is
`0|[1-9][0-9]*`, its numeric value cannot exceed `2^64-1`, and consumers must
use exact integer comparison. Operation sequence and Store transition sequence
remain the semantic ordering authorities; the exact timestamp is preserved for
transport fidelity and display.

Service namespace, name, and version come from the normalized resource object,
not duplicated Agent attributes. A nonzero loss counter, a missing required
slot, a sequence/count mismatch, or a failed Store reconstruction makes the
retrieved contract evidence partial. Zero counters alone do not claim that
arbitrary provider instrumentation was preserved; the integrity assessment is
limited to evidence owned by this contract.

Every normalized span interval is non-inverted: `end_time` is greater than or
equal to `start_time`. Consumers report `invalid_span_interval` rather than
coercing a negative duration.

### Failure and cancellation retain ownership

The operation that fails and the owning Agent span use OpenTelemetry error
status, `error.type`, and exception evidence. A parent Workflow or Node records
its own propagated failure according to the existing contract.

Execution cancellation uses `junjo.cancelled = true` and
`junjo.cancelled_reason` on each active owning span. Cancellation is not marked
as an error solely because it was cancelled.

Exception, cancellation, and Hook diagnostics cross one shared non-throwing
text projection before they reach span status, attributes, or events. This is
an observability projection, not an application-data repair boundary. A lone
Unicode surrogate is replaced with U+FFFD while the rest of the diagnostic is
preserved. If arbitrary `__str__`, callback-identity lookup, or traceback
formatting raises, the producer emits a stable portable fallback instead. The
SDK constructs standard OpenTelemetry exception event fields from that
projection rather than delegating untrusted formatting to `record_exception`.
Every emitted diagnostic string is therefore strict UTF-8, while the original
exception or `CancelledError` remains the execution value that is propagated.
Telemetry formatting can neither replace an already selected outcome nor turn
a Hook observer failure into an execution failure.

Task cancellation delivered during terminal observer dispatch occurs after the
executable outcome is committed and is not execution cancellation. The owning
executable span adds a `junjo.hook_delivery_cancelled` event with
`junjo.hook.event`, `junjo.hook.callback`, and
`junjo.hook.delivery.cancelled_reason`. It does not change outcome or terminal
reason, set `junjo.cancelled` or `junjo.cancelled_reason`, create an error
status, or emit a second terminal event. This is the telemetry counterpart of
ADR 0005's terminal boundary.

An absent model response, validated Tool arguments, Tool result, or Agent output
because an operation failed is different from present evidence transformed by
payload policy.

### Canonical fixtures own interoperability

Horizon 1 adds deterministic normalized Agent fixtures under two valid sets:

- `contracts/telemetry/fixtures/agent/producer` contains scenarios the Horizon
  1 full-policy Python producer must emit equivalently;
- `contracts/telemetry/fixtures/agent/consumer` contains contract-valid
  non-full-policy or transport-loss scenarios that Studio must consume but the
  initial Python producer cannot intentionally select.

Together they cover:

1. direct typed completion;
2. ordered multiple Tools;
3. first-Tool failure after whole-batch admission, with later admitted calls
   truthfully never started;
4. first-Tool cancellation after whole-batch admission, with later admitted
   calls truthfully never started;
5. Tool invoking a nested Workflow;
6. Agent invoked inside a Workflow Node;
7. nested Workflow failure propagation;
8. Agent failure inside a Workflow Node;
9. Agent cancellation inside a Workflow Node;
10. input and history boundary rejection with no Store or operations;
11. unknown Tool with no Tool span;
12. malformed Tool arguments with one preflight diagnostic Tool span;
13. malformed normalized model response with a serializable response candidate;
14. a non-serializable model response candidate;
15. ModelDriver failure;
16. Tool service failure;
17. Tool output validation failure with a serializable result candidate;
18. a non-serializable Tool result candidate;
19. Agent final-output validation failure;
20. an over-budget Tool batch with no admission, service, or side effect;
21. model-request limit exhaustion before another driver operation starts;
22. cancellation during a model request;
23. cancellation during a direct Tool service;
24. cancellation during a Workflow-backed Tool with nested Workflow evidence;
25. concurrent run isolation;
26. absent versus reported-zero model usage;
27. non-terminal hook failure followed by successful completion;
28. cancellation during a terminal observer after a completed Agent outcome;
29. `Agent -> Tool -> Workflow -> Node -> Agent` with both Agent operation
    sequences restarting at 1 to prove owner-scoped assembly;
30. an internal admission failure before a Store becomes public evidence;
31. an internal terminal-commit failure with explicit, truthful partial Store
    evidence;
32. an unexpected internal execution failure after admission;
33. standalone Agent execution beneath a non-Junjo ambient span without a
    fabricated semantic executable parent;
34. consumer-only explicit non-full payload modes, including redacted
    operation content and a live revision hidden by one coherent telemetry
    projection;
35. consumer-only explicit OTLP dropped-evidence counters producing partial
    evidence status; and
36. consumer-only Store policy-unavailable evidence that remains distinct from
    failed verification and not-applicable state.

A true no-op Store transition is a generic Store-v2 concern rather than a
fabricated Agent behavior. It is proved by a canonical Workflow transition and
the language-independent RFC 6902 Store replay vectors.

Fixtures prove hierarchy, identity, operation sequence, Store revision
reconstruction, payload modes, status ownership, terminal attributes, and
nested Graph preservation. A separate fingerprint fixture proves canonical
material and hashes, including the numeric and Unicode edge cases above.

The fixture envelope must permit Agent-only traces without a Workflow Graph.
The validator must discover both Workflow and Agent fixtures and validate
scenario-specific requirements.

Consumer-only corrupt derivatives live under
`contracts/telemetry/fixtures/invalid/agent`. Each has an expected diagnostic
code and mutates a valid canonical fixture to prove rejection of duplicate,
gapped, or out-of-range operation sequences; missing trailing, duplicate, or
gapped Store transitions; revision discontinuity; terminal-revision mismatch;
patch replay mismatch; required-slot omission; invalid payload-slot mode
combinations; count inequality or limit mismatch; noncontiguous model ordinal;
and duplicate or mismatched Tool call ID/ordinal. These are not valid producer
fixtures. The contract validator and Studio backend tests must reject each
derivative with its declared diagnostic.

The invalid set also includes raw duplicate-name JSON and unsafe-number or
invalid-Unicode cases. Those cases exercise strict decoding before an ordinary
language mapping can erase the defect.

SDK producer tests generate evidence semantically equivalent to every producer
fixture only. All valid producer and consumer fixtures directly drive ingestion
preservation and backend semantic assembly tests. Frontend tests consume the
typed backend projection generated from both valid sets through an integration
adapter; the frontend does not become a raw span interpreter and no hand-copied
canonical fixture competes with the shared contract.

## Implementation and release boundary

Agent runtime, Store v2 events, contract schemas, canonical fixtures, SDK
producer conformance, and Studio consumer support may be developed in stages on
one branch. They merge as one atomic repository contract change and publish
through coordinated, independently versioned SDK and Studio releases.

The greenfield cutover order is explicit:

1. merge the atomic repository change after all producer and consumer gates pass;
2. publish Python SDK `0.65.0`, the first version 2 producer;
3. prepare Studio `0.82.0` or newer by updating the canonical deployment SDK
   pin and compatibility statements to the now-installable `0.65.0` release,
   then publish the strict Studio images and generated deployment mirrors in
   one release transaction;
4. upgrade other application emitters and deploy the paired documentation.

Between steps 2 and 3, the deployed version 1 Studio is not a semantic consumer
for version 2 evidence. That temporary telemetry-diagnostics outage is accepted
for this greenfield cutover. After step 3, Studio rejects version 1 Junjo
semantic evidence. No dual parser, dual emission, fallback, or
production-availability mechanism is added.

Ingestion preserves the fields owned by this shared contract; this ADR does not
claim that Studio preserves every possible OTLP field. Studio interpretation is
owned by Studio ADR 007.

## Consequences

Agent execution is reconstructable and comparable without pretending it is a
Graph. Explicit operation and transition sequences remove timestamp ambiguity.
Stable Agent keys and structural fingerprints support cross-release analysis.

The first implementation is intentionally evidence-heavy. Full normalized
requests, responses, Tool values, and state can be large, and every Store
producer and consumer must update for version 2. Payload policy provides an
explicit future privacy and size boundary without weakening the proof.

## Rejected alternatives

- Model and Tool as `junjo.span_type` values: operations are not executables.
- Agent as a Workflow Graph: dynamic operations are not predeclared nodes.
- Timestamp-only ordering: exported timestamps do not define a reliable total
  order.
- Agent-only state events: Store revision semantics benefit every executable
  and should have one contract.
- Fingerprinting redacted snapshots: payload policy would change identity.
- Silent payload truncation: Studio could not distinguish missing from empty.
- Provider wire payload as the core contract: it would couple Studio to
  providers.
- Telemetry through hooks: optional observers cannot own diagnostics.
- SDK-only contract rollout: Studio would be unable to consume emitted
  semantics.

## Deferred decisions

- provider wire capture;
- hidden reasoning or chain-of-thought;
- public streaming chunks;
- parallel Tool operation ordering;
- multi-agent and handoff semantics;
- persistent memory and durable execution;
- MCP;
- token and cost enforcement;
- production retention, privacy, and access-control policy;
- evaluation, promotion, and evidence-search APIs.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0004: Agent ModelDriver and Tool contracts](0004-agent-model-driver-and-tool-contracts.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [Studio ADR 004: Span Events JSON Contract](../../apps/studio/docs/adr/004-events-json-contract.md)
- [Studio ADR 007: Agent execution diagnostics](../../apps/studio/docs/adr/007-agent-execution-diagnostics.md)

## Revision history

- 2026-07-14: Clarified portable JSON and generated-schema normalization across
  producer and consumer boundaries, added ambient non-Junjo parentage and
  Store-policy consumer scenarios, required typed handling of malformed raw
  JSON, and defined exact decimal-string OTLP event timestamps.
