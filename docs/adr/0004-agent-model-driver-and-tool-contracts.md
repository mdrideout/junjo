# ADR 0004: Agent ModelDriver and Tool contracts

- Status: Accepted
- Date: 2026-07-13
- Last clarified: 2026-07-14
- Owners: Junjo platform

## Context

The Agent execution loop needs one provider-neutral boundary for model
decisions and one application boundary for side effects. If either boundary
accepts provider SDK objects, arbitrary callables, mutable run state, or hidden
dependency injection, the core loop becomes difficult to test and provider
behavior begins to own Junjo semantics.

This ADR owns the typed Agent input, normalized transcript, ModelDriver, Tool,
usage, collaborator concurrency, validation, and boundary-error contracts. ADR
0003 owns the loop and terminal model. ADR 0005 owns Workflow composition. ADR
0006 owns emitted telemetry.

## Decision

### Public boundaries are typed and schema-capable

The initial Python API is generic over:

- `InputT`: application input for one Agent execution;
- `OutputT`: the required final Agent output;
- `DependenciesT`: opaque request-scoped application services;
- `ToolInputT` and `ToolOutputT` for each Tool.

Declared input and output types must be compatible with Pydantic
`TypeAdapter`, produce deterministic JSON Schema, and support JSON
serialization. Agent input, Agent output, and Tool output may be any JSON
value. Tool input must produce an object-root JSON Schema because portable
provider Tool calls use named argument objects. A scalar Tool argument requires
an explicit object wrapper with a named field.

“Object-root” is semantic rather than a requirement for a literal top-level
`type: "object"`. Core accepts a direct object schema, a local root-reference
chain that resolves to an object schema, an object-only `oneOf` or `anyOf`, or
an `allOf` with an object-valued constraint. It rejects nullable,
unconstrained, boolean, or mixed scalar/object roots. This permits recursive
models and discriminated unions without moving provider-specific schema
encoding rules into core.

This permits Pydantic models, dataclasses, typed containers, and appropriate
simple scalar outputs without requiring every boundary value to subclass one
base model.

Junjo validates and detaches data at every ownership boundary:

- execute input and history before Store creation or model work;
- ModelDriver responses before Agent state mutation;
- Tool arguments before Tool service invocation;
- Tool results before transcript commit;
- final output before successful result construction.

Caller-owned and provider-owned mutable objects never enter Agent state or a
detached result. Validation uses the declared adapter, and normalized JSON is
the language-independent diagnostic and driver boundary.

Input and history validation happens after the run identity and Agent span
exist so rejection is observable. It starts no ModelDriver or Tool operation.

### Normalized JSON is a portable owned boundary

Every value Junjo accepts into the normalized Agent model must remain exact
when it crosses Python, OpenTelemetry, JSON Schema, Studio's Rust and Python
services, and the TypeScript frontend. The owned JSON boundary therefore uses
the interoperable RFC 8785/I-JSON value domain everywhere, not only while
computing structural fingerprints:

- object names are strings and raw JSON with duplicate object names is
  rejected before it becomes a mapping;
- integers are limited to `[-(2^53-1), 2^53-1]`;
- floating-point values are finite binary64 values;
- strings and object names contain Unicode scalar values and no lone
  surrogates; and
- no implicit coercion, truncation, Unicode normalization, or last-name-wins
  parsing repairs an invalid value.

This rule covers application inputs and outputs, transcript content, Tool
arguments and results, ModelDriver settings and responses, usage facts, and
all normalized identifiers or text copied into requests or telemetry. A value
that cannot cross the boundary exactly is rejected at the earliest owned
constructor or validation boundary. Diagnostic candidate capture may report
that rejection, but it must not label missing or lossy content as full
evidence.

Declared validation has two explicit paths. A concrete JSON value is captured
once, validated in strict JSON mode, and must retain every supplied value; a
declared default may add a missing member. A non-JSON typed Python value is
validated with strict Python semantics, serialized through the declared
adapter, and must retain its exact type and compare equal after strict JSON
detachment. Both paths accept only the schema's external aliases, recursively
forbid undeclared members on structured objects, and require a stable second
round trip.

A raw numeric string therefore cannot become a number, a validator cannot
silently trim or case-fold supplied JSON, and a typed redacting or transforming
serializer cannot replace content while presenting the operation as lossless.
An explicitly declared typed `datetime`, UUID, or path remains valid when its
detached typed value is equal, but none can project into an unrelated string
boundary. Diagnostic evidence for a typed candidate is marked available only
after this losslessness proof; an invalid or lossy typed value has no truthful
full JSON candidate.

Junjo's schema profile closes structured object schemas with
`additionalProperties: false`. Open data is represented explicitly by a
`dict[str, T]` field or boundary, never by a structured model that silently
ignores or admits undeclared members. JSON object names map directly to Python
`str` keys. Set, frozenset, generator, and other one-shot iterable declarations
are unsupported because their deduplication, ordering, or consumption cannot
preserve concrete JSON-array semantics.

### Generated JSON Schema has one language-neutral profile

Declared adapters may generate equivalent schemas with language- or
class-specific presentation names. Before a schema enters a request,
definition snapshot, Tool or Agent fingerprint, Junjo normalizes it as
follows. Normalized validation and serialization schemas must first be
identical; asymmetric boundary schemas are a construction error.

1. close structured object schemas while preserving explicit `dict[str, T]`
   mapping schemas;
2. remove the JSON Schema `title` annotation from every schema object while
   preserving an application property whose name is literally `title`;
3. treat `$defs` and legacy `definitions` as the same local-definition
   facility;
4. canonicalize set-valued arrays: require uniqueness and sort property names
   in `required` and `dependentRequired`, strings in array-valued `type`, and
   `enum` values by their RFC 8785 encoding;
5. traverse schema object members in lexical order and order-sensitive schema
   arrays in their declared order, assigning reachable local definitions `d0`,
   `d1`, and so on when first referenced;
6. rewrite local `$ref`, local `$dynamicRef`, and discriminator mapping
   targets to those canonical `#/$defs/dN` names, including recursive and
   mutually recursive definitions; and
7. omit unreachable local definitions.

All other keywords and values remain part of the schema. This is normalization
of generated representation, not a general JSON Schema optimizer: Junjo does
not reorder applicator arrays such as `oneOf`, `anyOf`, or `allOf`, positional
arrays such as `prefixItems`, or presentation arrays such as `examples`. It
does not infer broader semantic equivalence or erase descriptions, defaults,
examples, constraints, discriminator data, or application property names. A
dangling local definition reference or duplicate member in a set-valued array
is a construction error.

### The transcript is provider-neutral and closed

Agent history and run transcript use immutable normalized messages. The initial
closed message model contains:

- `AgentInputMessage` with one normalized JSON application input;
- `AssistantOutputMessage` with one normalized JSON final output;
- `AssistantToolCallsMessage` with optional assistant text and a non-empty
  ordered tuple of normalized Tool calls;
- `ToolResultMessage` with Tool-call ID, Tool name, and normalized JSON result.

A normalized Tool call contains:

- an opaque non-empty call ID;
- a declared Tool name;
- a JSON object of arguments.

Tool-call IDs must be unique within one Agent run. The ModelDriver is
responsible for converting provider identifiers into run-unique normalized
identifiers while preserving provider ordering.

Application-supplied history must contain complete prior exchanges. It cannot
contain an unresolved Tool call, a Tool result without its call, a duplicate
normalized call ID, or provider SDK objects. Junjo validates and copies the
history before appending the current `AgentInputMessage`.

This transcript is an execution record, not persistent memory. The application
selects and stores history outside the Agent.

### ModelRequest is immutable normalized intent

One `ModelRequest` contains detached values:

- Agent key and run ID;
- 1-based model-request ordinal;
- exact instructions;
- the ordered normalized message transcript;
- ordered normalized Tool definitions;
- the declared final-output JSON Schema.

A normalized Tool definition contains its stable name, description, input
schema, and output schema. Provider APIs may expose only the fields they
support, but the ModelDriver receives the complete Junjo definition.

`ModelRequest` contains no application dependencies, private Store, hooks,
spans, provider credentials, or arbitrary callable references. Provider
settings remain in the configured ModelDriver descriptor unless Junjo later
standardizes a setting across every driver.

### ModelResponse is a disjoint union

The asynchronous ModelDriver contract is one request to one fully assembled
normalized response:

- `FinalOutputResponse` contains one normalized JSON output candidate and
  optional usage;
- `ToolCallsResponse` contains a non-empty ordered tuple of normalized Tool
  calls, optional assistant text, and optional usage.

A response cannot contain both a final output and Tool calls, or neither.
Either condition is a malformed response. Assistant text accompanying Tool
calls is retained in the transcript but does not become a final output.

Missing or duplicate Tool-call IDs, non-object arguments, and any other closed
response invariant violation raise `AgentModelResponseError` before Tool
preflight.

The initial contract has no partial response type. A provider adapter may
consume a provider stream internally, but it returns one assembled response.
Partial chunks do not enter Agent state, public lifecycle, or application
transport.

### ModelDriver translates providers and nothing else

A `ModelDriverBinding` owns the immutable descriptor plus exactly one shared
driver instance or one synchronous per-run factory. The descriptor exists
before a factory product and is the only driver identity used in structural
material.

The ModelDriver protocol has no competing descriptor property. Driver products
translate requests for the identity declared by their binding.

A ModelDriver owns:

- provider client invocation;
- provider request encoding;
- provider response decoding;
- internal provider-stream assembly;
- provider error classification;
- normalized usage extraction.

The binding-owned descriptor contains:

- a stable driver key;
- provider identity;
- model identity;
- behavior-affecting configuration safe to include in structural material.

Credentials, mutable clients, callbacks, and arbitrary Python object identity
are not descriptor data.

The Agent runtime, not the ModelDriver, owns:

- looping and transcript state;
- Tool resolution and invocation;
- limits and budget admission;
- final-output validation;
- lifecycle and cancellation semantics;
- result construction;
- Junjo semantic telemetry.

A ModelDriver never executes a Tool, retries an Agent step, mutates the supplied
request, or returns provider SDK objects.

### Usage is reported fact, not policy

Normalized usage supports optional non-negative provider-reported values:

- input tokens;
- output tokens;
- cached input tokens;
- reasoning tokens;
- total tokens.

Absence is distinct from zero. The runtime records per-response usage and
aggregates supplied values while preserving how many responses contributed to
each field. It does not invent unsupported values or derive money amounts from
provider pricing tables.

The initial kernel reports usage but does not enforce token or cost limits.

### Tool is an explicit application capability

A Tool definition contains:

- one stable, case-sensitive name matching
  `^[A-Za-z_][A-Za-z0-9_-]{0,63}$`;
- one clear description;
- a declared input adapter and JSON Schema;
- a declared output adapter and JSON Schema;
- either a shared service or a per-run service factory.

The Tool name is its logical identity within the initial Agent contract. Tool
names must be unique within an Agent definition. A ModelDriver binding may
impose a stricter provider constraint during Agent construction. Tool structural
identity is derived from the declared name, description, and schemas; it never
depends on Python class, function, module, or memory identity.

Construction requires no decorator, docstring parsing, global registration, or
signature inference.

The Tool service is asynchronous and receives only:

- validated `ToolInputT`;
- a read-only `AgentRunContext[DependenciesT]`.

The run context exposes opaque dependencies plus immutable Agent key,
definition ID, run ID, Tool-call ID, and call ordinal. It does not expose the
private Agent Store, transcript, counters, lifecycle dispatcher, or telemetry
objects.

The call ordinal is the contiguous 1-based position across all normalized Tool
calls requested in the run, including calls later rejected before service
invocation. It is not the Tool operation-span sequence or an admitted-call
counter.

Tool services own application work and side effects. A recoverable domain
failure must be represented explicitly in `ToolOutputT`. Junjo never converts
an arbitrary exception into model-visible text.

### A Tool batch is preflighted before side effects

For every `ToolCallsResponse`, the runtime performs this complete preflight
before constructing or invoking any Tool service in the batch:

1. count the calls as requested and verify that the entire batch fits the
   remaining admission budget;
2. inspect calls in model order, resolving each Tool and validating and
   detaching its argument object;
3. fail deterministically on the first unknown Tool or invalid argument;
4. only after every call passes, mark the entire batch admitted.

If any preflight step fails, no Tool service in that response runs, and no call
in that batch is admitted. Valid calls preceding the failing call do not receive
execution spans. ADR 0006 permits one preflight diagnostic Tool span for the
first declared Tool whose arguments fail validation; an unknown Tool has no
Tool span.

After successful preflight, Tools execute sequentially in model-returned order.
Each validated result is committed before the next Tool begins. The next model
request begins only after every Tool result in the batch has been committed.

If a later Tool service fails, earlier completed side effects and results remain
real and diagnostically visible. Junjo provides no implicit rollback,
transaction, or compensation.

Parallel Tool execution is deferred until capability metadata can distinguish
read-only, mutating, ordered, and transaction-sensitive work.

### Collaborator lifetime is explicit

ModelDriver and Tool service bindings have two mutually exclusive forms:

- a shared instance whose owner guarantees reentrancy and concurrent safety;
- a per-run factory.

Junjo does not inspect collaborator internals and does not hide unsafe shared
objects behind a serializing lock. Shared instances are a caller guarantee.
Initial factory callables are synchronous, zero-argument, and must themselves
be reentrant because one definition may invoke them from concurrent runs.
Request-scoped application services belong in `DependenciesT` rather than
factory arguments.

The ModelDriver factory is called lazily inside the first model operation. Each
Tool service factory is called lazily inside that Tool's first admitted
operation. A product is cached and reused only within that run. Unused Tool
factories are never called.

A ModelDriver factory failure is `AgentModelError`. A Tool service factory
failure is `AgentToolError` with Tool and call identity. Factory products do
not carry a second descriptor and therefore cannot compete with the binding's
identity.

Initial factories return collaborators that require no Agent-owned asynchronous
cleanup. Database sessions, HTTP client lifetimes, and other managed resources
belong in application dependencies. A future managed-collaborator contract
requires a separate lifecycle decision.

Deterministic tests use per-run factories unless a scripted collaborator is
intentionally stateless and reentrant.

### Invalid definitions fail at construction

Configuration errors are not execution outcomes and create no run or telemetry.
Construction validates:

- non-empty Agent key and positive limits;
- valid and unique Tool names;
- schema generation and object-root Tool input;
- exactly one shared instance or factory per binding;
- complete ModelDriver descriptor and all other structural material within ADR
  0006's canonicalizable I-JSON domain.

The provider-neutral Agent contract owns the Tool-name grammar. A provider
adapter may reject a name it cannot encode when translating a request, but the
core does not add a second driver-specific construction contract or advertise
provider-specific Tool-name compatibility through `ModelDriverBinding`.

`AgentConfigurationError` is the separate construction-error root;
`ModelDriverConfigurationError` and `ToolConfigurationError` specialize it at
their owning boundaries. This hierarchy is outside the run-bound `AgentError`
hierarchy: configuration failures have no run ID, terminal reason, Store
snapshot, or execution telemetry. Provider credentials and network
availability are not construction checks.

### Boundary failures are explicit

The initial public error hierarchy distinguishes:

- `AgentAdmissionError` for unexpected Junjo-owned preparation failure before
  Store availability is published;
- `AgentInputValidationError`;
- `AgentHistoryValidationError`;
- `AgentLimitExceededError` for model-request or Tool-call budget exhaustion;
- `AgentModelError` for a ModelDriver exception;
- `AgentModelResponseError` for a malformed normalized response;
- `AgentUnknownToolError`;
- `AgentToolInputValidationError`;
- `AgentToolError` for a Tool service exception;
- `AgentToolOutputValidationError`;
- `AgentOutputValidationError`;
- `AgentInternalError` for unexpected Junjo-owned machinery after admission,
  including a failed terminal state transaction.

Admission, input, and history errors are `AgentInvocationError` values. The
remaining errors are `AgentExecutionError` values. Both derive from
`AgentError` and follow ADR 0003's detached diagnostic contract. When an
underlying exception exists, it is retained as the cause. Tool-related errors
include Tool name and call identity.

`AgentLimitExceededError` carries the exhausted limit kind, positive effective
limit, attempted next count, and the requested Tool-batch size when a whole
batch is rejected. No operation from the rejected budget unit starts.

`asyncio.CancelledError` is never wrapped, retried, or converted to a Tool
result. Drivers and Tool services must be cancellation-cooperative.

The runtime validates a final output once. It does not automatically ask the
model to repair invalid output. Retries, backoff, fallback providers, and
model-visible error recovery require explicit future policies.

### Core ships contracts, not provider ownership

Horizon 1 adds the provider-neutral protocols, normalized types, and a
deterministic scripted ModelDriver test utility. It does not add a provider SDK
dependency to Junjo core.

The `ai_chat` proof uses an application-local deterministic ModelDriver with no
provider SDK or live provider call. An official adapter or optional provider
package is considered only after the normalized contract is proven by more
than one real use.

## Implementation requirements

Deterministic tests must prove:

- every supported schema-capable input and output boundary is detached;
- invalid input or history starts no model or Tool work;
- request and response objects contain no provider SDK values;
- direct output and ordered multi-Tool responses;
- rejection of both/neither response variants;
- construction rejection for invalid limits, bindings, names, and schemas;
- typed model-request and Tool-batch limit exhaustion before affected work;
- run-unique Tool-call correlation;
- whole-batch preflight before side effects;
- sequential Tool execution and result ordering;
- Tool output validation before transcript commit;
- lazy factory caching, factory failure mapping, and shared-safe behavior under
  concurrency;
- preservation of absent versus zero usage;
- every typed failure and unwrapped cancellation;
- no automatic output correction or hidden retry.

## Consequences

The private Agent loop can be deterministic and provider-neutral while Tools
remain ordinary application capabilities. Provider adapters stay thin because
they translate data rather than controlling execution.

Applications must declare schemas and dependency boundaries explicitly.
Provider-specific conveniences do not leak into the core contract, and
applications must choose whether mutable collaborators are shared-safe or
per-run.

## Rejected alternatives

- Provider SDK messages in Agent state: they couple state and replay to one
  provider.
- Arbitrary callable introspection: it hides schemas, identity, and validation.
- ModelDriver-owned Tool execution: it moves orchestration outside Junjo.
- Automatic exception-to-text conversion: it makes failure policy implicit.
- Implicit collaborator locking: it hides unsafe ownership and serializes
  unrelated runs.
- Parallel Tools initially: side-effect ordering is not yet declared.
- Automatic output repair: it creates an unrequested second decision loop.
- Official provider packages in the first kernel: one proof is insufficient to
  establish a durable packaging boundary.

## Deferred decisions

- official provider adapters and package locations;
- retries, backoff, provider fallback, caching, and middleware;
- dynamic Tool registration and MCP;
- public incremental streaming;
- parallel Tool policies;
- token and cost enforcement;
- multi-agent handoffs;
- managed collaborator cleanup.

## Related decisions

- [ADR 0003: Agent execution model](0003-agent-execution-model.md)
- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)

## Revision history

- 2026-07-14: Clarified the portable JSON domain for every normalized Agent
  boundary and specified deterministic language-neutral JSON Schema
  normalization for structural identity and ModelDriver requests.
- 2026-07-14: Removed the unimplemented requirement for declarative
  driver-specific Tool-name compatibility. The shared Tool-name grammar remains
  the construction contract; provider encoding errors remain at the provider
  adapter boundary.
