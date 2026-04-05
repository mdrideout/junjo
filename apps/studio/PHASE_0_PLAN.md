# Phase 0 Plan

## Purpose

- This document defines the concrete work required to complete Phase 0 of the Junjo library update refactor in `junjo-ai-studio`.
- Phase 0 is the transport-contract lock phase.
- It exists to prove that the current Junjo payload survives the AI Studio data path unchanged before any frontend interpretation refactor begins.
- This is a greenfield refactor.
- No backward compatibility, fallbacks, shims, migrations, adapters, or dual-schema support are in scope.
- The target state is current Junjo only.

## Why Phase 0 Exists

- The library update changed Junjo’s frontend-relevant telemetry model:
- `junjo.id` -> `junjo.executable_runtime_id`
- `junjo.parent_id` -> `junjo.parent_executable_runtime_id`
- `junjo.definition_id` -> `junjo.executable_definition_id`
- `junjo.parent_definition_id` -> `junjo.parent_executable_definition_id`
- `junjo.workflow.graph_structure` -> `junjo.workflow.execution_graph_snapshot`
- The graph snapshot payload now uses compiled-graph runtime and structural identity fields.
- Failed spans now use standard span-level `error.type`.
- Hook failures now arrive as `junjo.hook_error` events on surrounding spans.
- State changes are attributed to the active executable identity.

- The refactor will go wrong if it assumes the backend or ingestion layers need Junjo-specific rewrites when they are actually generic OTEL transport.
- The refactor will also go wrong if it trusts existing frontend assumptions rather than the current end-to-end payload.
- Phase 0 fixes that by freezing the actual current contract that later phases will consume.

## Greenfield Constraints

- Do not test or preserve old Junjo keys like:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- `junjo.workflow.store_id`
- Do not add dual-schema test fixtures.
- Do not add compatibility assertions.
- Do not normalize Junjo fields in backend or ingestion just to make frontend work easier.
- Treat current Junjo output as the only supported contract.

## Source Of Truth

- Junjo library migration notes:
- `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md`
- Junjo AI Studio docs:
- `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst`
- Junjo OpenTelemetry docs:
- `/Users/matt/repos/junjo/docs/opentelemetry.rst`
- Junjo runtime emission points:
- `/Users/matt/repos/junjo/src/junjo/workflow.py`
- `/Users/matt/repos/junjo/src/junjo/store.py`
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`
- `/Users/matt/repos/junjo/src/junjo/graph.py`
- `/Users/matt/repos/junjo/src/junjo/node.py`
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`
- `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py`

## Current End-To-End Data Path

- OTLP ingestion entry:
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/trace_service.rs`
- OTLP spans are converted into `SpanRecord` values.
- `SpanRecord` stores generic OTEL transport fields plus JSON-serialized `attributes`, `events`, and `resource_attributes`.
- No Junjo-specific normalization happens in ingestion.

- WAL and Parquet persistence:
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/schema.rs`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/arrow_wal.rs`
- The stored schema is generic and stable:
- `span_id`
- `trace_id`
- `parent_span_id`
- `service_name`
- `name`
- `span_kind`
- `start_time`
- `end_time`
- `duration_ns`
- `status_code`
- `status_message`
- `attributes`
- `events`
- `resource_attributes`

- Backend hot/cold coordination:
- `/Users/matt/repos/junjo-ai-studio/proto/ingestion.proto`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/internal_service.rs`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/span_ingestion/ingestion_client.py`
- The backend receives snapshot file paths and recent cold file paths.
- It does not receive Junjo-specific parsed data from ingestion.

- Cold metadata indexing:
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/parquet_indexer/parquet_reader.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/db_sqlite/metadata/indexer.py`
- The only Junjo-specific field used here is `junjo.span_type`.
- That field is still valid in the updated library.

- Query and delivery:
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/repository.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/router.py`
- DataFusion parses the JSON blobs back to `attributes_json` and `events_json`.
- The backend still returns generic OTEL dictionaries for observability endpoints.

- Frontend boundary:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/fetch/get-trace-spans.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- This is the first place where Junjo-specific interpretation starts.

## Key Architectural Conclusion

- Ingestion does not need a Junjo schema rewrite.
- Persistence does not need a Junjo schema rewrite.
- Internal gRPC does not need a Junjo schema rewrite.
- DataFusion does not need a Junjo schema rewrite.
- REST delivery does not need a Junjo schema rewrite.
- The primary runtime break is in the frontend Junjo interpretation layer.
- Phase 0 must prove this rigorously so later phases can refactor with confidence.

## Phase 0 Objective

- Capture and verify the exact current-Junjo payload as it appears after transport through AI Studio.
- Establish a canonical fixture corpus for the current library.
- Add transport-fidelity tests that fail if the payload changes or is mutated by ingestion/query layers.
- Provide the stable foundation that Phase 1 through Phase 6 will build on.

## Phase 0 Non-Goals

- Do not implement the new frontend graph schema.
- Do not rewrite `SpanAccessor`.
- Do not change selectors, Mermaid rendering, or state panels.
- Do not alter backend observability endpoint shapes.
- Do not add compatibility support for old Junjo payloads.
- Do not redesign product semantics for subflow state views or graph selection.

## What Phase 0 Must Prove

- The following current Junjo attributes survive transport unchanged:
- `junjo.span_type`
- `junjo.executable_definition_id`
- `junjo.executable_runtime_id`
- `junjo.executable_structural_id`
- `junjo.parent_executable_definition_id`
- `junjo.parent_executable_runtime_id`
- `junjo.parent_executable_structural_id`
- `junjo.enclosing_graph_structural_id`
- `junjo.workflow.execution_graph_snapshot`
- `junjo.workflow.store.id`
- `junjo.workflow.parent_store.id`
- `junjo.workflow.node.count`
- `junjo.workflow.state.start`
- `junjo.workflow.state.end`
- `error.type`
- `junjo.cancelled`
- `junjo.cancelled_reason`

- The following events survive transport unchanged:
- standard `exception`
- `junjo.hook_error`
- `set_state`

- The same semantic payload is correct in all relevant retrieval modes:
- hot-only
- cold-only
- fused hot+cold
- workflow-listing queries using `junjo.span_type == "workflow"`

- The backend does not mutate or rename current Junjo fields.
- The frontend generic OTEL schemas can parse the real returned payloads.

## Current Gaps

- Existing frontend OpenAPI contract tests are not enough because observability endpoints are still typed as `dict[str, Any]`, which will not catch Junjo field-level changes.
- Existing backend DataFusion tests only lightly cover generic JSON parsing and an old-style `junjo.span_type` example.
- Existing ingestion tests verify snapshot existence and basic query behavior, not current-Junjo payload fidelity.
- Existing OTLP integration test helpers are duplicated across tests instead of being shared.
- There is no single canonical current-Junjo fixture corpus in the repo.

## Phase 0 Strategy

- Use one canonical fixture corpus.
- Use the backend API payload shape as the semantic source of truth for the fixture corpus.
- Reuse the existing ingestion-service integration harness rather than inventing a parallel test stack.
- Extend current backend and ingestion tests instead of building a second testing surface.
- Keep assertions semantic:
- parse JSON
- compare objects and event structures
- do not compare unstable serialized strings
- Separate transport fidelity from frontend interpretation:
- Phase 0 locks the transport contract
- later phases consume it

## Canonical Fixture Strategy

- Create a shared fixture directory at:
- `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update/`

- Create fixture files for the current library only.
- Do not store old-schema fixtures here.

- Recommended fixture set:
- `basic_workflow_success.json`
- `subflow_with_parent_store.json`
- `run_concurrent_success.json`
- `failed_executable_with_error_type.json`
- `cancelled_executable.json`
- `hook_failure_on_surrounding_span.json`

- Canonical fixture format:
- backend-style observability payloads, not old frontend helper formats
- each fixture should model one trace as a list of spans
- each span should include:
- `trace_id`
- `span_id`
- `parent_span_id`
- `service_name`
- `name`
- `kind`
- `start_time`
- `end_time`
- `status_code`
- `status_message`
- `attributes_json`
- `events_json`
- optional helper metadata in a top-level fixture envelope is fine if it improves readability

- Fixture design rules:
- every field present must correspond to current Junjo output
- every example must be minimal but representative
- graph snapshots should be valid current `junjo.workflow.execution_graph_snapshot` payloads
- event examples must include realistic `exception`, `junjo.hook_error`, and `set_state` attributes
- fixture IDs should be deterministic and readable where possible

## Workstream 1: Shared Test Builders And Fixture Loaders

- Problem:
- backend OTLP request construction is duplicated across multiple integration tests
- fixture loading is not standardized

- Work required:
- add shared backend test helper module for:
- OTLP `KeyValue` builders
- OTLP span builders
- OTLP export request builders
- current-Junjo trace case builders
- add shared backend fixture loader for the canonical fixture corpus
- add shared frontend fixture loader for the same corpus

- Proposed backend helper location:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_transport_builders.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_fixture_loader.py`

- Proposed frontend helper location:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/test-utils/junjo-fixture-loader.ts`

- Robustness requirements:
- one helper should build OTLP spans directly from current-Junjo semantic case definitions
- avoid hand-writing protobuf payloads repeatedly in each test
- fixture loading should validate that required files exist and fail loudly

## Workstream 2: Ingestion Serialization Fidelity Tests

- Problem:
- `span_record.rs` currently has narrow coverage and does not prove that current Junjo attributes and events survive serialization intact

- Target file:
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`

- Work required:
- add tests for `SpanRecord::from_otlp()` covering:
- `junjo.workflow.execution_graph_snapshot` preserved as string
- `junjo.executable_runtime_id` preserved
- `junjo.executable_structural_id` preserved
- `error.type` preserved
- `junjo.cancelled` and `junjo.cancelled_reason` preserved
- `junjo.hook_error` event preserved with `exception.*` and `junjo.hook.*`
- `set_state` event preserved with `timeUnixNano` and attributes
- resource `service.name` preserved

- Robustness requirements:
- assert semantic JSON contents after serialization
- do not only assert “non-empty”
- include arrays and nested objects where current Junjo uses them
- preserve the existing `timeUnixNano` camelCase guarantee

## Workstream 3: Backend Query Fidelity Unit Tests

- Problem:
- `test_datafusion_query.py` proves generic query behavior but does not lock the current Junjo payload

- Target file:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`

- Work required:
- add helper-backed tests for:
- cold-only query returns current Junjo attrs/events intact
- hot-only query returns current Junjo attrs/events intact
- fused query returns current Junjo attrs/events intact
- dedup does not erase current Junjo attrs/events
- workflow-only query still selects workflow spans using current `junjo.span_type`

- Specific assertions to add:
- graph snapshot string exists at `attributes_json["junjo.workflow.execution_graph_snapshot"]`
- parsed graph snapshot contains expected top-level `graphStructuralId`
- failed span exposes `attributes_json["error.type"]`
- cancelled span exposes `attributes_json["junjo.cancelled"]`
- hook failure span contains `events_json` event named `junjo.hook_error`
- `set_state` event survives with `timeUnixNano`

- Robustness requirements:
- use the canonical fixture corpus
- compare parsed semantic structures
- test both single-tier and fused-tier paths

## Workstream 4: Ingestion-Service Integration Fidelity Tests

- Problem:
- current integration tests verify transport mechanics, snapshots, and race conditions, but not current-Junjo semantic fidelity

- Reuse existing harness:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/conftest.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_prepare_hot_snapshot_integration.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_flush_index_bridge_integration.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_prepare_hot_snapshot_flush_race_integration.py`

- Work required:
- create a new backend integration test module dedicated to current-Junjo payload transport fidelity
- ingest current-Junjo-shaped OTLP spans using the shared builders
- verify:
- hot snapshot parquet contains the expected attributes/events
- backend `get_fused_trace_spans()` returns the same semantic payload
- `get_fused_workflow_spans()` still finds workflow spans
- after `flush_wal()`, cold-only retrieval still preserves the payload
- the flush/index bridge preserves current Junjo payloads, not just span existence

- Proposed file:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_junjo_transport_contract_integration.py`

- Minimum scenarios:
- basic workflow trace
- subflow trace
- run-concurrent trace
- failure trace
- hook failure trace

- Robustness requirements:
- validate all relevant retrieval paths:
- immediate hot query
- post-flush cold query
- fused query
- recent-cold bridge path where metadata is not indexed yet
- assert exact span IDs and expected semantic fields

## Workstream 5: Cold Metadata And Workflow Discovery Sanity Tests

- Problem:
- `junjo.span_type` remains valid, but Phase 0 should prove that workflow discovery still works with the current fixture corpus

- Target files:
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/parquet_indexer/parquet_reader.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/db_sqlite/metadata/indexer.py`
- backend tests that cover indexing and workflow discovery

- Work required:
- add or extend tests so the canonical current-Junjo workflow fixture proves:
- workflow spans are still recognized by `junjo.span_type == "workflow"`
- cold indexing still supports workflow-file discovery
- no additional Junjo-specific indexing is needed for current library support

- Robustness requirements:
- this should remain narrow
- do not overfit SQLite metadata to Junjo graph identity
- keep indexing generic except for existing workflow and llm shortcuts

## Workstream 6: Frontend Generic Contract Parse Gate

- Problem:
- frontend contract tests based on OpenAPI mocks cannot protect the observability payload because the backend returns generic dictionaries

- Target files:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- new frontend tests using the canonical fixture corpus

- Work required:
- add a frontend test that loads the shared current-Junjo fixture corpus and proves `OtelSpanSchema` can parse it
- optionally add a light schema-level assertion for:
- `attributes_json` contains the expected current Junjo keys
- `events_json` contains expected event names

- Proposed file:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/junjo-transport-contract.test.ts`

- Robustness requirements:
- Phase 0 frontend tests must stay generic
- do not start validating future accessor logic here
- the goal is to prove the real backend payload shape is accepted

## Required Phase 0 Scenarios

- `basic_workflow_success`
- includes workflow span
- includes current graph snapshot
- includes node spans
- includes `set_state`

- `subflow_with_parent_store`
- includes workflow span
- includes subflow span
- includes `junjo.workflow.store.id`
- includes `junjo.workflow.parent_store.id`

- `run_concurrent_success`
- includes workflow span
- includes `run_concurrent` span
- includes child executable spans

- `failed_executable_with_error_type`
- includes failed workflow, subflow, node, or run-concurrent span
- includes `error.type`

- `cancelled_executable`
- includes `junjo.cancelled`
- includes `junjo.cancelled_reason`

- `hook_failure_on_surrounding_span`
- includes `junjo.hook_error`
- includes `exception.*`
- includes `junjo.hook.*`

## Required Phase 0 Assertions

- Attribute names are current Junjo names only.
- Graph snapshot is available under `junjo.workflow.execution_graph_snapshot`.
- Graph snapshot remains parseable JSON after transport.
- Events retain original names and expected attributes.
- `set_state` still uses `timeUnixNano`.
- `error.type` remains a span attribute.
- `junjo.hook_error` remains an event, not a synthetic span.
- Workflow discovery via `junjo.span_type == "workflow"` still works.
- Fused query does not alter semantic payload compared with hot-only or cold-only retrieval.

## Recommended Execution Sequence

- Step 1: create the canonical fixture directory and current-Junjo trace cases
- Step 2: add shared backend and frontend fixture loaders
- Step 3: add ingestion serialization tests in `span_record.rs`
- Step 4: expand `backend/tests/test_datafusion_query.py`
- Step 5: add current-Junjo ingestion-service integration tests
- Step 6: add workflow discovery sanity coverage if still missing
- Step 7: add frontend schema parse tests against the shared fixtures
- Step 8: run the smallest relevant test commands and fix any transport inconsistencies before Phase 1 begins

## Proposed Test Commands For Phase 0 Validation

- Ingestion tests:
- `cd /Users/matt/repos/junjo-ai-studio/ingestion && cargo test --locked`

- Backend targeted tests:
- `cd /Users/matt/repos/junjo-ai-studio/backend && uv run pytest tests/test_datafusion_query.py`
- `cd /Users/matt/repos/junjo-ai-studio/backend && uv run pytest tests/test_prepare_hot_snapshot_integration.py -m requires_ingestion_service`
- `cd /Users/matt/repos/junjo-ai-studio/backend && uv run pytest tests/test_flush_index_bridge_integration.py -m requires_ingestion_service`
- `cd /Users/matt/repos/junjo-ai-studio/backend && uv run pytest tests/test_prepare_hot_snapshot_flush_race_integration.py -m requires_ingestion_service`
- `cd /Users/matt/repos/junjo-ai-studio/backend && uv run pytest tests/test_junjo_transport_contract_integration.py -m requires_ingestion_service`

- Frontend targeted tests:
- `cd /Users/matt/repos/junjo-ai-studio/frontend && npm run test:run -- junjo-transport-contract`

## Robustness Rules For Implementation

- Use one shared fixture corpus.
- Do not duplicate equivalent payloads in backend and frontend trees.
- Use semantic comparisons, not raw string equality, for JSON payloads.
- Keep test helpers explicit and single-purpose.
- Prefer builders over repeated literal protobuf construction.
- Keep observability transport tests current-library-only.
- Fail loudly when expected fields are missing.
- Keep Phase 0 separate from Phase 1 logic so transport and interpretation do not get conflated.

## Risks If Phase 0 Is Weak

- Later phases may “fix” the frontend around guessed payloads rather than the real contract.
- Hidden backend or ingestion mutations may go unnoticed until late UI work.
- OpenAPI contract tests may give false confidence because observability endpoints are still generic dict payloads.
- The refactor may accidentally preserve old keys or build dual-schema logic despite greenfield goals.
- Graph or failure refactors may be built against invalid fixtures and fail again when real traces arrive.

## Phase 0 Exit Criteria

- The repo contains a canonical current-Junjo fixture corpus at the project root.
- Ingestion serialization tests prove current Junjo attributes and events survive JSON serialization.
- Backend query tests prove hot, cold, and fused queries preserve the current Junjo payload.
- Integration tests prove current-Junjo payloads survive the ingestion service and bridge paths.
- Frontend generic OTEL schemas parse the real backend-style payload fixtures.
- No Phase 0 test uses or preserves old Junjo keys.
- Later phases can assume the AI Studio transport contract is stable and focus entirely on interpretation and rendering.

## Deliverables

- `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update/`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_transport_builders.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_fixture_loader.py`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/test-utils/junjo-fixture-loader.ts`
- expanded `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs` tests
- expanded `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`
- new `/Users/matt/repos/junjo-ai-studio/backend/tests/test_junjo_transport_contract_integration.py`
- new `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/junjo-transport-contract.test.ts`

## Relationship To Later Phases

- Phase 0 does not solve frontend breakage.
- Phase 0 makes later phases safe:
- Phase 1 can rewrite the frontend Junjo accessor against a locked contract.
- Phase 2 can replace graph schemas against a locked graph snapshot payload.
- Phase 3 can rebuild Mermaid correlation against locked runtime and structural fields.
- Phase 4 can replace legacy exception logic against locked `error.type` and `junjo.hook_error` behavior.
- Phase 5 can rewrite state/store attribution against locked `set_state` and current store keys.

## Bottom Line

- Phase 0 is successful when the repo can ingest or synthesize current Junjo traces and prove that AI Studio preserves the current Junjo payload unchanged from OTLP ingress to frontend-ready API payloads.
- Once that is true, the rest of the refactor is a frontend interpretation and product behavior rewrite, not a transport rewrite.
