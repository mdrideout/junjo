# ADR-004: Span Events JSON Contract

## Status
Accepted

## Last revised

2026-07-13 for telemetry contract version 2.

## Context

Junjo stores span events in the Parquet `events` column as a JSON string. The Python backend exposes this as `events_json` and the frontend parses these events for:

- `set_state` rendering inside workflow span trees
- workflow state diffs (“Before/After/Changes/Detailed”)
- exception views

This is a cross-service contract: ingestion writes the canonical transport
shape, raw backend APIs pass it through, and semantic backend features validate
and interpret the shared telemetry contract before the frontend presents it.

A regression occurred when ingestion serialized event timestamps using the OTLP proto field name `time_unix_nano` (snake_case), while the frontend schema expects the JavaScript OTel JSON style `timeUnixNano` (camelCase). The result was that `set_state` events existed but were silently dropped by schema parsing, breaking the workflow state UI.

## Decision

Define the canonical JSON shape for event objects stored in Parquet and returned by the backend:

- `name`: string
- `timeUnixNano`: canonical unsigned 64-bit decimal string
- `attributes`: JSON object mapping string keys to JSON values
- `droppedAttributesCount`: non-negative integer

The fourth field is active in telemetry contract version 2 following the
atomic rollout required by root ADR 0006. Studio supports only the active
contract; version 1 is unsupported after the greenfield cutover.

Specifically:

- The timestamp field name MUST be `timeUnixNano` (camelCase).
- The timestamp value MUST be decimal text matching `0|[1-9][0-9]*` and no
  greater than `18446744073709551615`. It is text because OTLP's unsigned
  64-bit nanosecond domain cannot be represented exactly by JavaScript JSON
  numbers. Ingestion performs the integer-to-decimal encoding once; raw APIs
  preserve it; semantic consumers validate it; and frontend ordering uses
  exact integer comparison rather than `Number` coercion.
- The OTLP Event `dropped_attributes_count` field MUST be stored and returned as
  `droppedAttributesCount` (camelCase). Telemetry contract version 2 requires
  this field, including zero, so loss is distinguishable from an old or
  incomplete event shape.
- The ingestion service is the source of truth for this encoding.
- Raw backend trace APIs treat `events` as an opaque JSON blob and return it as
  `events_json` without rewriting.
- Semantic Workflow and Agent backend features may parse this canonical shape
  through shared contract validators. They return typed semantic projections;
  the frontend does not independently reinterpret raw Agent events.

## Consequences

- Adding the required loss counter in contract version 2 is a breaking shape
  change for previously written Parquet files. The greenfield cutover adds no
  compatibility coercion.
- Ingestion unit tests enforce both camelCase keys and exact counter
  preservation, including exact serialization of the unsigned 64-bit maximum.
- Frontend contract and ordering tests cover adjacent timestamps above the
  JavaScript safe-integer boundary.
- Contract fixtures and backend tests prove that a nonzero dropped-attribute
  count produces partial evidence integrity rather than silently complete
  diagnostics.

## Related

- `ingestion/src/wal/span_record.rs` (event JSON serialization)
- `frontend/src/features/traces/schemas/schemas.ts` (`JunjoSetStateEventSchema`, `JunjoExceptionEventSchema`)
- [Root ADR 0006: Agent telemetry contract](../../../../docs/adr/0006-agent-telemetry-contract.md)
- [ADR-007: Agent execution diagnostics](007-agent-execution-diagnostics.md)
