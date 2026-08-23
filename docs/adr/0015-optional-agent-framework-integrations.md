# ADR 0015: Optional external Agent framework integrations

- Status: Accepted
- Date: 2026-08-18
- Owners: Junjo platform and Python SDK

## Context

Some applications use an external Agent framework as their outer interactive
runtime while needing Junjo's opinionated Workflow, Agent, state, concurrency,
telemetry, and evaluation mechanics for selected application operations.
Requiring those applications to replace their outer Agent would make Junjo a
competing harness rather than an additive application framework.

The first concrete integration is the OpenAI Agents SDK. It already owns its
Agent loop, tools, handoffs, guardrails, model adapters, sessions, and native
tracing callbacks. Junjo must compose through those public boundaries without
adding OpenAI dependencies to the default SDK, copying traces from a hosted
dashboard, or fabricating Junjo identity for external spans.

## Decision

### Integrations are optional first-party modules

The Python distribution exposes the OpenAI integration through the
`openai-agents` optional dependency group and the
`junjo.plugins.openai_agents` namespace. The default `junjo` import has no
OpenAI dependency or import side effect.

One optional integration does not justify a generic runtime plugin registry,
entry-point discovery, a separate distribution, or a universal Agent framework
protocol. Those remain deferred until another concrete integration proves
stable shared requirements.

### Composition uses framework-native tools

The OpenAI integration supplies explicit adapters that expose a Junjo Workflow
or Junjo Agent as an OpenAI function tool. Each adapter requires application
owned input validation, fresh execution construction, dependency mapping,
output projection, and cleanup. It adds no hidden Store sharing, retry,
recovery, transaction, or global budget.

Failure and cancellation propagate through the ordinary owning boundaries.
OpenTelemetry context establishes physical parentage. Native Junjo executions
retain their definition, runtime, structural, Store, result, and semantic
parent identity.

### The application owns telemetry lifecycle

One explicit integration operation wraps the active OpenAI Agents
`TraceProvider` and translates its first-party Trace and Span objects into an
application-owned OpenTelemetry `TracerProvider`. The operation returns an
ownership handle that restores the exact original OpenAI provider. It never
replaces or shuts down the OpenTelemetry provider or a Junjo exporter.

The wrapper delegates normal OpenAI tracing behavior to the original provider,
including application-configured native processors. Whether OpenAI-hosted trace
export remains configured is an application decision made before installing
Junjo. Importing the integration does not mutate process-global state.

### First-party OpenAI traces are translated to OpenTelemetry

The OpenAI Agents SDK's own Trace and Span objects are the authoritative source
for Agent, tool, model, handoff, guardrail, task, turn, MCP, custom, speech, and
transcription activity. The integration translates those objects directly to
OpenTelemetry spans in the application's existing provider. It does not patch
the OpenAI HTTP client or emit a second model span for the same Agents SDK
operation.

Studio receives the translated spans through its existing authenticated OTLP
trace path. Studio does not copy OpenAI-hosted traces or add an OpenAI-specific
ingestion endpoint.

External spans retain appropriate standard `gen_ai.*` projections plus one
versioned Junjo OpenAI Agents envelope containing the complete structured
source data available for that Trace or Span. They do not receive
`junjo.span_type`, Junjo executable definition or runtime IDs, or native Junjo
Agent semantics. Native Junjo descendants continue to emit the active Junjo
telemetry contract unchanged.

The OpenAI Agents per-run sensitive-data setting owns whether prompts,
responses, arguments, and results are present in the source objects. Junjo
records what that source policy makes available and does not independently
recover redacted data. Source tracing API keys are credentials, not telemetry,
and are never serialized into the Junjo envelope.

Every concrete source span type in the locked OpenAI Agents dependency has an
explicit mapping and test. Unknown future types retain a generic, lossless
representation at runtime while a coverage sentinel requires maintainers to
review new current types deliberately.

### Studio presents one mixed trace

The ordinary Studio trace view presents the complete physical hierarchy using
standard GenAI labels and native Junjo labels. Native Junjo Workflow and Agent
pages remain semantic views and link back to the full trace. External Agents
are not inserted into native Junjo Agent queries or assigned fabricated native
identity.

### External Agent evaluation remains application-local

The optional integration may declare an external Agent evaluation target. The
real application process runs it under the existing bounded Junjo evaluation
subject span. The target returns the evaluator subject and a truthful
OpenTelemetry span evidence reference. Dataset, Run, Case, and Attempt remain
Studio's evaluation identities; trace and span IDs are only physical evidence
pointers.

The evaluation result remains binary. This decision adds no score, hosted
application executor, uploaded source bundle, or alternate evaluation
framework.

## Consequences

- OpenAI Agents applications can adopt Junjo incrementally.
- Junjo retains no opinion about the application's model provider.
- The optional integration adds no dependency or runtime work to base Junjo.
- Mixed traces use one application provider and Studio's existing trace-only
  ingestion architecture.
- The application can preserve or replace OpenAI-native trace processors before
  installing Junjo without Junjo silently changing that policy.
- One versioned integration envelope preserves source-specific fields without
  pretending they are native Junjo telemetry.
- A second external framework integration can be evaluated from concrete
  repetition rather than anticipated abstractions.
- OpenAI Agents tracing interfaces and concrete source types become an explicit
  compatibility surface backed by locked examples, coverage sentinels, and span
  fixtures.

## Rejected alternatives

- Replace the external Agent runtime with Junjo Agent: adoption is additive.
- Add OpenAI dependencies to base Junjo: unrelated applications must not pay
  the dependency or lifecycle cost.
- Build a universal Agent runtime adapter first: one integration does not prove
  a truthful abstraction.
- Copy data from the OpenAI trace dashboard: Studio consumes live OTLP evidence.
- Retag external spans as Junjo executables: this makes identity and native
  semantic views untruthful.
- Use third-party OpenTelemetry instrumentors as the primary bridge: they omit
  current OpenAI Agents source types and duplicate model activity when combined
  with direct HTTP-client instrumentation.
- Patch the OpenAI HTTP client in addition to translating Agents spans: the
  Agents SDK source span is the single owner for an Agents model operation.
- Configure telemetry on import: process lifecycle remains application-owned.
- Add Studio metrics for the integration: Studio remains trace-only under ADR
  0012.

## Related decisions

- [ADR 0005: Agent and Workflow composition](0005-agent-workflow-composition.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
- [ADR 0012: Studio integration is trace-only](0012-studio-trace-only-telemetry-integration.md)
- [ADR 0013: Application-executed Studio evaluations](0013-application-executed-studio-evaluations.md)
- [ADR 0014: Bounded evaluation telemetry context](0014-evaluation-telemetry-context.md)
- [Studio ADR 010: Evaluation control persistence and API](../../apps/studio/docs/adr/010-evaluation-control-persistence-and-api.md)
