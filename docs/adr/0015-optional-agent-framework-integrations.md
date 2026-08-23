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

One explicit integration operation attaches the supported official OpenAI
OpenTelemetry instrumentors to an application-owned `TracerProvider`. The
operation returns an ownership handle that removes only registrations it made.
It never replaces or shuts down the provider or a Junjo exporter.

Existing official instrumentation is not installed a second time. Existing
OpenAI-hosted trace export remains enabled unless the application explicitly
disables it. Importing the integration does not mutate process-global state.

### Standard OpenTelemetry is the evidence boundary

The integration uses official OpenTelemetry GenAI instrumentation for OpenAI
Agent, tool, and model operations. Studio receives those spans through its
existing authenticated OTLP trace path. Studio does not copy OpenAI-hosted
traces or add an OpenAI-specific ingestion endpoint.

External spans retain standard `gen_ai.*` semantics. They do not receive
`junjo.span_type`, Junjo executable definition or runtime IDs, or native Junjo
Agent semantics. Native Junjo descendants continue to emit the active Junjo
telemetry contract unchanged.

The integration maintains an explicit coverage matrix for OpenAI-native trace
types. A narrow companion processor may represent materially missing runtime
operations only when the official instrumentor does not emit them. It must not
duplicate officially emitted Agent, Workflow, Tool, or model spans.

Prompt, response, argument, and result capture remains an explicit application
privacy choice. The integration does not silently enable process-wide content
capture.

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
- A second external framework integration can be evaluated from concrete
  repetition rather than anticipated abstractions.
- Official GenAI instrumentation maturity becomes an explicit compatibility
  surface backed by locked examples and span fixtures.

## Rejected alternatives

- Replace the external Agent runtime with Junjo Agent: adoption is additive.
- Add OpenAI dependencies to base Junjo: unrelated applications must not pay
  the dependency or lifecycle cost.
- Build a universal Agent runtime adapter first: one integration does not prove
  a truthful abstraction.
- Copy data from the OpenAI trace dashboard: Studio consumes live OTLP evidence.
- Retag external spans as Junjo executables: this makes identity and native
  semantic views untruthful.
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
