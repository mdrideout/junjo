# ADR-013: API key attribution of spans

## Status

Accepted on 2026-10-05, on the maintainer's decision to add filtering by API
key before the first release of the Rust backend.

## Date

2026-10-05

## Context

Ingestion admits an export only after the backend has validated its API key
([ADR-009](009-bounded-ingestion-api-key-validation.md)). Once admitted, the
spans carried nothing that said which key had sent them. An operator who
gives each application or environment its own key could not ask Studio for
one key's traces.

The release that first ships the Rust backend already requires a reset of
stored telemetry ([ADR-011](011-rust-backend-and-single-origin-studio.md)).
A new stored column costs no migration now and would cost one later.

## Decision

### Every stored span records the identifier of the key that sent it

- The internal key check answers with the valid key's identifier beside its
  validity. The identifier is the key's `id`. The key value never leaves the
  backend's database and the request that carries it.
- Ingestion caches the identifier with the positive validation, under the
  rules of ADR-009. The window, the capacity, and what is cached when are
  unchanged.
- Ingestion writes the identifier as one more column of the stored span,
  `api_key_id`, in the write-ahead log, the hot snapshot, and cold Parquet.
  Every span of one export shares it.
- The identifier is storage metadata. It is not part of the telemetry
  contract, it is not an attribute of the span, and the raw span API does not
  return it.

### A listing can ask for one key

The three service listings (spans, root spans, and Workflow spans) accept an
API key identifier and then return only the spans that key sent. The filter
is applied by the query engine with the listing's other filters. The metadata
index is not involved: it still selects files by service.

The Traces page offers the active keys by name. The Workflow executions page
does not yet: its list is shared state that other pages read, and changing it
is a separate piece of work.

### A deleted key keeps its record

Deleting a key deactivates it. Its row stays, with its identifier and name
and without the key value. It stops validating within the window of ADR-009
and leaves the key list.

- Spans a deleted key sent keep their identifier and stay in the listing of
  every key.
- A deleted key is not offered as a filter.
- The key value is cleared at deletion. A revoked secret has no further use,
  and the record does not need it.

## Consequences

- One low-cardinality text column is added to every stored span. It
  dictionary-encodes to almost nothing in Parquet.
- Stored telemetry from before this decision lacks the column. A listing
  without a key filter still reads such files. A listing with one fails on
  them. The release's reset removes them.
- A backend and an ingestion service from different sides of this decision do
  not work together: ingestion refuses a validation that does not name the
  key. The two are released and deployed as one version.
- The application database gains `deleted_at` on API keys, and its schema
  version is 4.

## Alternatives considered

- **Store the key's name.** Rejected: a name can be shared and is not an
  identity.
- **Carry the key as a span or resource attribute.** Rejected: it would enter
  the telemetry an application sent, and a filter on it would parse JSON for
  every span.
- **Record keys per file in the metadata index.** Deferred. It would let a
  filtered listing skip files that hold none of the key's spans. No
  measurement shows the need.
- **Remove a deleted key's row.** Rejected on the maintainer's decision: the
  record of which key an identifier named should outlive the key.
