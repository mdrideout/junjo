# ADR-004: Span Events JSON Contract

## Status
Accepted

## Context

Junjo stores span events in the Parquet `events` column as a JSON string. The Python backend exposes this as `events_json` and the frontend parses these events for:

- `set_state` rendering inside workflow span trees
- workflow state diffs (“Before/After/Changes/Detailed”)
- exception views

This is a cross-service contract: **ingestion writes**, **backend passes through**, **frontend parses**.

A regression occurred when ingestion serialized event timestamps using the OTLP proto field name `time_unix_nano` (snake_case), while the frontend schema expects the JavaScript OTel JSON style `timeUnixNano` (camelCase). The result was that `set_state` events existed but were silently dropped by schema parsing, breaking the workflow state UI.

## Decision

Define the canonical JSON shape for event objects stored in Parquet and returned by the backend:

- `name`: string
- `timeUnixNano`: number
- `attributes`: JSON object mapping string keys to JSON values

Specifically:

- The timestamp field name MUST be `timeUnixNano` (camelCase).
- The ingestion service is the source of truth for this encoding.
- The backend should treat `events` as an opaque JSON blob and return it as `events_json` without rewriting.

## Consequences

- Changing event field names is a breaking change for previously written Parquet files.
- A small ingestion unit test should enforce the `timeUnixNano` key to prevent regressions.

## Related

- `ingestion/src/wal/span_record.rs` (event JSON serialization)
- `frontend/src/features/traces/schemas/schemas.ts` (`JunjoSetStateEventSchema`, `JunjoExceptionEventSchema`)
