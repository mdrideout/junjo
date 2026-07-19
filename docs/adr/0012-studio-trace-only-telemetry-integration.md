# ADR 0012: Studio integration is trace-only

- Status: Accepted
- Date: 2026-07-18
- Owners: Junjo platform, Python SDK, and Studio

## Context

Junjo AI Studio's ingestion service implements the OTLP trace service. It does
not implement the OTLP metrics service, a metrics storage contract, or metric
query and presentation surfaces.

`JunjoOtelExporter` nevertheless created both an OTLP span exporter and an OTLP
metric exporter. Every configured exporter therefore also created a periodic
metric-reader worker. In a live application, that worker sent requests Studio
could not serve and received `UNIMPLEMENTED`. This was not a partial metrics
feature: metric data had no supported ingestion-to-query path.

Studio targets low-resource environments. Adding a background worker, periodic
network work, warnings, and shutdown ownership for an unsupported signal spends
resources while making the public integration contract misleading. Conversely,
adding an OTLP metrics receiver merely to make the requests succeed would create
a new persistence and product architecture without a decided retention, query,
cardinality, or resource-budget contract.

## Decision

The Junjo AI Studio integration is trace-only until metrics are designed and
accepted as a complete cross-platform capability.

`JunjoOtelExporter` exposes one `BatchSpanProcessor` through
`span_processor`. It does not create or expose a metric exporter,
`PeriodicExportingMetricReader`, or `metric_reader` property. Its `flush()` and
`shutdown()` helpers operate only on the Junjo-owned span processor. Normal
applications retain a `TracerProvider` for their process lifetime and shut down
that provider at process termination.

SDK examples and Studio deployment examples that configure Junjo AI Studio
create only the Studio trace pipeline. They do not install a `MeterProvider` on
Studio's behalf.

Studio-owned deployment examples and compatibility harnesses configure the
standard OTLP trace exporter directly. This keeps Studio's ingestion boundary
explicit and lets those artifacts remain correct while they intentionally pin a
previously published SDK release. SDK-owned examples use the current
`JunjoOtelExporter` convenience surface.

This decision does not narrow Junjo's compatibility with OpenTelemetry or
prevent application metrics. An application may independently configure a
`MeterProvider` and metric exporter for a third-party OpenTelemetry destination.
That provider remains application-owned and is not modified by the Studio
integration.

Adding Studio metrics later requires a separate accepted decision covering the
whole signal path together:

- OTLP metrics service and authentication;
- bounded ingestion, batching, and backpressure behavior;
- persistence schema, retention, compaction, and cardinality limits;
- hot and cold query semantics;
- backend and frontend query and presentation contracts;
- deployment resource budgets and measured low-resource performance; and
- SDK configuration, lifecycle, tests, and documentation.

## Consequences

- Studio-bound applications no longer run a metric-export worker that can only
  fail against Studio.
- Idle memory, thread, wakeup, network, and log overhead are lower and lifecycle
  ownership is simpler.
- Trace and Store evidence used by Studio is unchanged. The telemetry contract
  and its canonical span fixtures do not change.
- `JunjoOtelExporter.metric_reader` is removed as an intentional breaking public
  API change, and `shutdown()` no longer accepts the metric-reader-only timeout
  argument. Callers using the removed surface must remove that Studio metric
  pipeline or configure a separate metric destination.
- Studio documentation must describe OTLP trace ingestion precisely. Generic
  OpenTelemetry documentation may still describe metrics when it is not
  claiming that Studio accepts them.

## Rejected alternatives

- Keep the metric reader and document the `UNIMPLEMENTED` warnings: knowingly
  running a failing background pipeline is not a supported integration.
- Keep a no-op `metric_reader` compatibility surface: it would hide signal loss
  and preserve confusing lifecycle ownership.
- Silently accept and drop OTLP metrics in ingestion: successful transport must
  not imply durable or queryable telemetry.
- Add only the OTLP metrics RPC: transport without bounded storage, retention,
  query semantics, and user-visible behavior is an incomplete architecture.
- Send metrics through the trace schema: different OpenTelemetry signals retain
  their standard contracts and must not be disguised as one another.

## Related decisions

- [ADR 0001: Junjo platform monorepo](0001-junjo-platform-monorepo.md)
- [ADR 0006: Agent telemetry contract](0006-agent-telemetry-contract.md)
- [ADR 0009: Unified documentation publishing](0009-unified-documentation-publishing.md)
