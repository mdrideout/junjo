# ADR 0007: Application execution correlation and Studio resolution

- Status: Accepted
- Date: 2026-07-14
- Last clarified: 2026-07-15
- Owners: Junjo platform

## Context

Junjo gives every Workflow and Agent execution its own runtime identity, while
OpenTelemetry gives every recorded span a physical trace and span identity.
Neither identity is the durable application-domain identity of the user action
that caused the execution.

The AI Chat proof has a server-created Turn identity plus Workflow and Agent
runtime identities. It can persist the runtime identities, but the existing
Studio detail routes require trace and span identities. The application must
not query Studio's physical storage, persist full telemetry records, or make
its domain identity equal to an OpenTelemetry trace ID.

This decision owns application correlation at Junjo executable boundaries and
resolution of a semantic runtime identity to Studio diagnostic routes. It does
not make telemetry application persistence or expose Studio credentials to an
application browser.

## Decision

### Domain, execution, and telemetry identities remain distinct

An application owns its domain identity. For AI Chat this is a server-created
Turn ID. Junjo owns Workflow and Agent runtime IDs. OpenTelemetry owns trace and
span IDs.

No one identity substitutes for another:

- a Turn ID identifies an accepted application action;
- a Workflow or Agent runtime ID identifies one Junjo execution;
- a trace and span ID locate recorded telemetry evidence.

Applications persist Junjo runtime IDs as execution references. They do not
persist telemetry payloads as application state.

### Correlation is explicit, immutable execution input

Junjo exposes one immutable `ExecutionCorrelation` value with:

- a portable non-empty `type` selected by the application; and
- a portable non-empty `id` selected by the trusted application boundary.

A top-level `Workflow.execute()` or `Agent.execute()` call may receive this
value. Nested Junjo executables inherit the active value automatically. A
nested caller cannot replace an active correlation with a different one.

Correlation does not enter Workflow or Agent Store state automatically. It is
not a Tool dependency, Graph identity, lifecycle control input, or source of
authorization policy. The application passes its own domain ID through its
state and dependencies when domain behavior needs it.

Junjo emits the pair on executable owner spans as:

- `junjo.correlation.type`;
- `junjo.correlation.id`.

Both attributes are present or both are absent. Operation spans do not repeat
the pair because their owning executable is already explicit. Studio may index
the owner attributes for later domain-correlation queries.

The active telemetry contract remains version 2. The normalized fixture schema
already permits governed attribute extensions, and this decision adds an
optional all-or-none pair without changing any required version 2 execution,
Store, payload, or Agent semantics. Canonical correlated fixtures and producer
and consumer tests are required in the same implementation.

### Correlation is not OpenTelemetry Baggage

In-process propagation uses Junjo's run-local execution context. Junjo does
not place application correlation in OpenTelemetry Baggage implicitly.

An application that propagates correlation across a network boundary must
validate that input at its trusted server boundary and construct a new
`ExecutionCorrelation`. Junjo does not treat propagated headers as trusted
domain identity.

### Studio resolves runtime identity

Studio owns one authenticated execution-resolution boundary addressed by:

- normalized service namespace;
- service name;
- executable type (`workflow`, `subflow`, or `agent`); and
- Junjo executable runtime ID.

Resolution selects executable owner spans only. Exactly one match returns its
trace ID, span ID, executable type, and Studio-relative diagnostic route. No
match returns not found. Multiple matches return an explicit evidence conflict;
Studio never selects the newest match.

The service scope is required because Junjo runtime IDs are portable execution
identities, not a Studio-global namespace contract.

Studio also owns an authenticated semantic execution route. Applications link
to this route rather than constructing Studio's physical detail routes. The
semantic route is a content route, not a holding screen:

- it renders the authenticated Studio shell and requested execution identity
  immediately;
- a missing resolution means telemetry is still arriving, so the page shows an
  in-context pending state and continues resolution with capped backoff for as
  long as the page remains open;
- it renders the ordinary Agent, Workflow, or trace detail surface when the
  physical identity becomes available; and
- it keeps the semantic URL as the canonical application link.

There is no user-visible attempt counter or ingestion deadline. An unresolved
execution is not an error merely because telemetry has not arrived yet. Invalid
semantic input, authorization failure, an ambiguous identity, transport
failure, and backend failure remain explicit errors.

Telemetry readiness and telemetry integrity are separate. Readiness answers
whether Studio can locate the execution. Integrity answers whether the located
telemetry is complete and internally coherent. A pending page makes no claim
about integrity, and a resolved page may still show integrity diagnostics.

### Debug presentation does not change execution

Applications may expose Studio links through an explicit runtime debug
configuration. The setting controls presentation only:

- execution references are always persisted;
- correlation and telemetry behavior do not change;
- no Studio API key is sent to the application browser; and
- Studio remains responsible for authenticating the person following a link.

## Consequences

Application objects, Junjo runs, and physical telemetry remain independently
addressable while retaining deterministic links between them. Nested Workflow
and Agent telemetry can be found from one trusted application correlation
without storing trace internals in the application. A deep link is useful as
soon as an application has a runtime ID, including while telemetry is in
flight.

The SDK gains a small public execution-input value and run-local propagation.
Studio gains an exact resolver feature and URL contract. Cross-process
correlation remains an application responsibility until a separate transport
contract is accepted.

## Rejected alternatives

- Client-created Turn IDs: request data is not an authoritative domain identity.
- Trace ID as Turn ID: it couples product persistence to one telemetry attempt.
- Runtime ID as Turn ID: one domain action and one executable run have different
  lifecycles.
- Store correlation only in Workflow state: nested executables and standalone
  Agents would not receive one uniform diagnostic identity.
- Put correlation in Baggage automatically: propagated baggage is not a trusted
  application boundary and is not automatically recorded as span attributes.
- Return trace and span IDs from every Junjo result: it makes application
  results depend on physical telemetry concerns and duplicates Studio routing.
- Let the application query raw Studio spans: it reverses the evidence-plane
  ownership boundary.
- Bounded resolver holding screen followed by redirect: ingestion latency is
  not an execution failure, attempt counts are implementation detail, and the
  semantic application link should remain stable.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
- [ADR 0008: Versioned application object persistence](0008-versioned-application-object-persistence.md)
- [Studio ADR 007: Agent execution diagnostics](../../apps/studio/docs/adr/007-agent-execution-diagnostics.md)
