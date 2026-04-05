# Library Update Refactor Plan

## Scope

- Goal: refactor Junjo AI Studio to support the current Junjo library only.
- Constraint: greenfield target state only. No backward compatibility, shims, migrations, adapters, or dual-schema support.
- Primary source of truth for the library update:
- `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:6-70`
- `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst:342-407`
- `/Users/matt/repos/junjo/docs/opentelemetry.rst:234-360`
- `/Users/matt/repos/junjo/src/junjo/workflow.py:212-265`
- `/Users/matt/repos/junjo/src/junjo/store.py:168-237`
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py:619-642`
- `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py:9-27`

## End-To-End Data Flow Baseline

- OTLP ingress starts at `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/trace_service.rs:43-149`.
- The ingestion service does not interpret Junjo-specific keys. It converts each OTLP span into a `SpanRecord` and serializes span attributes and events as opaque JSON strings. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs:27-66`
- The persisted WAL and Parquet schema is fixed OTEL transport plus JSON blobs:
- `span_id`, `trace_id`, `parent_span_id`, `service_name`, `name`, `span_kind`, `start_time`, `end_time`, `duration_ns`, `status_code`, `status_message`, `attributes`, `events`, `resource_attributes`. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/schema.rs:6-21`
- Hot snapshots and cold Parquet flushes preserve the same schema and do not normalize Junjo fields. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/arrow_wal.rs:193-320`
- The backend only receives hot snapshot paths and recent cold file paths over internal gRPC. It does not receive Junjo-normalized span payloads from ingestion. `/Users/matt/repos/junjo-ai-studio/proto/ingestion.proto:5-46` `/Users/matt/repos/junjo-ai-studio/backend/app/features/span_ingestion/ingestion_client.py:96-143`
- Cold-file indexing only extracts lightweight metadata for SQLite. The only Junjo-specific field it depends on is `junjo.span_type`, which remains valid in the current Junjo library. `/Users/matt/repos/junjo-ai-studio/backend/app/features/parquet_indexer/parquet_reader.py:162-175` `/Users/matt/repos/junjo-ai-studio/backend/app/db_sqlite/metadata/indexer.py:115-123`
- DataFusion queries return a generic OTEL API payload with `attributes_json` and `events_json` parsed back into JSON values. Junjo-specific interpretation starts after this point. `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py:395-468` `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py:608-651`
- The frontend fetchers and `OtelSpanSchema` only validate the generic OTEL shape and are still structurally compatible with the library update. `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/fetch/get-trace-spans.ts:7-22` `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts:15-33`
- Conclusion: the Junjo library update does not require a storage, ingestion, gRPC, or REST contract rewrite. The break begins at the frontend Junjo interpretation layer.

## Layer Impact Summary

- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/trace_service.rs`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/schema.rs`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/arrow_wal.rs`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/internal_service.rs`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/features/span_ingestion/ingestion_client.py`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/repository.py`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/router.py`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/features/parquet_indexer/parquet_reader.py`.
- No runtime code change required in `/Users/matt/repos/junjo-ai-studio/backend/app/db_sqlite/metadata/indexer.py`.
- Validation and test additions are required across ingestion and backend to prove the current Junjo payload survives the pipeline unchanged.
- The primary refactor surface is the frontend Junjo domain layer, graph parsing/rendering/correlation, failure handling, and state/store attribution.

## Confirmed Junjo Changes Driving This Refactor

- Junjo replaced `junjo.id` with `junjo.executable_runtime_id`. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:11`
- Junjo replaced `junjo.parent_id` with `junjo.parent_executable_runtime_id`. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:12`
- Junjo replaced `junjo.definition_id` with `junjo.executable_definition_id`. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:13`
- Junjo replaced `junjo.parent_definition_id` with `junjo.parent_executable_definition_id`. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:14`
- Junjo replaced `junjo.workflow.graph_structure` with `junjo.workflow.execution_graph_snapshot`. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:15`
- Workflow and subflow spans now emit explicit runtime, definition, structural, enclosing-graph, and store fields. `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst:356-386` `/Users/matt/repos/junjo/src/junjo/workflow.py:234-265`
- The execution graph snapshot now uses compiled graph identities:
- `graphStructuralId`
- `nodeRuntimeId`
- `nodeStructuralId`
- `edgeStructuralId`
- `tailNodeRuntimeId`
- `tailNodeStructuralId`
- `headNodeRuntimeId`
- `headNodeStructuralId`
- subflow structural and runtime linkage fields
- run-concurrent child-node fields. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:17-37`
- Mermaid node-to-span mapping is no longer “one Junjo ID everywhere.” It is now split between runtime and structural matching depending on node kind. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:38-49` `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst:388-405`
- Trace ancestry must still use OTEL `parent_span_id`, not Junjo parent executable fields. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:51-61`
- Failed executable spans now use standard span-level `error.type` in addition to status/error event behavior. `/Users/matt/repos/junjo/docs/opentelemetry.rst:239-249` `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py:9-13`
- Hook callback failures are now `junjo.hook_error` events on the surrounding span rather than standalone hook-error spans. `/Users/matt/repos/junjo/src/junjo/_lifecycle.py:619-642`
- `set_state` telemetry is attributed to the active executable identity, and spans now carry enough identity to reason about that cleanly. `/Users/matt/repos/junjo/src/junjo/store.py:181-237`

## Required Refactor Decisions

- Keep ingestion, persistence, internal gRPC, SQLite metadata, DataFusion, and REST payloads generic.
- Do not add a backend compatibility or normalization layer for Junjo-specific identity fields.
- Make the frontend Junjo domain layer the sole owner of executable identity parsing, graph snapshot parsing, failure classification, and store attribution.
- Keep `parent_span_id` as the trace-tree source of truth.
- Use Junjo parent executable fields only where the product needs execution-level relationships rather than OTEL ancestry.
- Render and correlate graph nodes using the execution graph snapshot and Junjo’s runtime-or-structural matching rules.
- Treat `run_concurrent` as a first-class selectable executable in the graph.
- Replace “exceptions” as the only failure concept with a current-Junjo failure model built from:
- `error.type`
- standard `exception` events
- `junjo.hook_error` events
- `junjo.cancelled`
- Make an explicit product decision for subflow state views. Recommended target state: a selected subflow defaults to its own `junjo.workflow.store.id`, and parent-store state changes are shown explicitly rather than inferred through legacy fallback logic.

## Phase 0: Lock The Transport Contract Before Refactoring

- Objective: prove exactly what the current Junjo payload looks like after it passes through ingestion, Parquet, DataFusion, and the REST API.
- Problem: the refactor will guess incorrectly if it is built from frontend assumptions rather than current end-to-end payloads.
- Library update tie-in: the new fields that must survive transport are `junjo.workflow.execution_graph_snapshot`, `junjo.executable_*`, `junjo.parent_executable_*`, `junjo.enclosing_graph_structural_id`, `error.type`, and `junjo.hook_error`.
- E2E data flow touched: OTLP span -> `SpanRecord.attributes/events` -> WAL/Parquet -> hot snapshot/cold Parquet -> DataFusion `attributes_json/events_json` -> frontend fetch.
- Code change required in `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`: add coverage for current Junjo workflow, subflow, node, run-concurrent, failure, cancellation, and hook-error payload shapes rather than only the old `junjo.span_type` smoke test.
- Code change required in `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`: add serialization tests that explicitly prove arbitrary string attributes, `error.type`, and `junjo.hook_error` events survive JSON serialization unchanged.
- Code change required in a new backend fixture location such as `/Users/matt/repos/junjo-ai-studio/backend/tests/fixtures/junjo_library_update/`: store current-Junjo OTEL payload examples or post-query API payload examples that the frontend and backend tests can share conceptually.
- Code change required in a new frontend fixture location such as `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/__fixtures__/junjo-library-update/`: mirror the API payload that the frontend will actually consume, not an invented frontend-only shape.
- Validation gate for this phase: the captured fixture must prove that the backend returns the current Junjo graph snapshot as the value of `attributes_json["junjo.workflow.execution_graph_snapshot"]`, preserves `error.type`, preserves `junjo.hook_error`, and preserves `set_state` events.
- Main risk: skipping this phase will produce a refactor that hardcodes a guessed graph snapshot or failure model and repeats the same breakage with new names.

## Phase 1: Rewrite The Frontend Junjo Domain Contract

- Objective: replace all legacy Junjo key access with a clean target-state executable identity contract.
- Problem: the first broken integration point is `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`, which still reads removed keys:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- stale `junjo.workflow.store_id`
- Library update tie-in: Junjo renamed those fields and now emits explicit executable runtime, definition, structural, parent-executable, graph-structural, and store fields. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:6-16` `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst:356-386`
- E2E data flow touched: `attributes_json` is still the generic API contract, but AI Studio’s typed Junjo access layer must now interpret the current keys and current graph snapshot name.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`: replace the old key constants with current Junjo keys and expose getters for:
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
- `error.type`
- `junjo.cancelled`
- `junjo.cancelled_reason`
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`: remove legacy helpers such as `junjoId`, `junjoParentId`, `workflowGraphStructure`, and the stale `workflowStoreId` implementation that reads `junjo.workflow.store_id`.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`: keep `OtelSpanSchema` generic, but add current-Junjo helper schemas for:
- `junjo.hook_error`
- standard `exception`
- `set_state`
- any small typed helpers needed for frontend classification.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`: stop encoding Junjo-specific assumptions as if they are limited to `exception` and `set_state` only.
- Validation gate for this phase: a frontend unit test must be able to parse current-Junjo spans and derive the correct runtime, structural, graph snapshot, store, and failure fields with no fallback logic.
- Main risk: if legacy getters remain available, old matching logic will keep leaking into selectors and graph code.

## Phase 2: Replace The Execution Graph Snapshot Schema And View Model

- Objective: make AI Studio’s graph model match Junjo’s compiled execution graph snapshot exactly.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts` and `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts` still assume the old graph payload shape:
- node `id`
- edge `source`
- edge `target`
- edge `condition`
- `subflowId`
- `isSubgraph`
- `children`
- legacy subflow source/sink fields
- Library update tie-in: the graph payload is now `junjo.workflow.execution_graph_snapshot` and uses compiled graph runtime and structural identity fields. `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md:17-37`
- E2E data flow touched: Junjo emits the execution graph snapshot as a JSON string attribute on workflow/subflow spans, ingestion and backend preserve it untouched, and the frontend must parse it into a current graph view model.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`: replace the old graph Zod schema with the current execution snapshot schema:
- `graphStructuralId`
- nodes with `nodeRuntimeId`, `nodeStructuralId`, `nodeType`, `nodeLabel`
- `isConcurrentSubgraph`
- `childNodeRuntimeIds`
- `isSubflow`
- `subflowGraphStructuralId`
- `subflowSourceNodeRuntimeId`
- `subflowSourceNodeStructuralId`
- `subflowSinkNodeRuntimeIds`
- `subflowSinkNodeStructuralIds`
- edges with `edgeStructuralId`, `tailNodeRuntimeId`, `tailNodeStructuralId`, `headNodeRuntimeId`, `headNodeStructuralId`, `edgeConditionLabel`, `edgeScope`, `parentSubflowRuntimeId`
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`: replace the old `workflowGraphStructure` parser with a new `workflowExecutionGraphSnapshot` parser that accepts the current string value and returns the new graph schema.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`: stop treating the graph as an old generic edge/node model and instead build a first-class compiled-graph view model with explicit runtime and structural lookup maps.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`: make the graph builder aware of:
- normal executable nodes
- subflow container nodes
- subflow internal structural nodes
- run-concurrent container nodes
- edge scopes
- top-level graph structural identity
- Validation gate for this phase: the frontend must be able to parse current-Junjo basic workflow, subflow, and run-concurrent graph snapshots without any compatibility path or guessed fields.
- Main risk: if the graph view model keeps collapsing runtime and structural identity into one “node id,” graph correlation will remain unstable and incorrect.

## Phase 3: Rebuild Mermaid Rendering And Graph-To-Span Correlation

- Objective: align rendering and click/highlight correlation with Junjo’s compiled-graph semantics and explicit matching rules.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx` currently assumes rendered Mermaid node IDs map directly to `wrapSpan(span).junjoId`, which is based on the removed `junjo.id` attribute.
- Problem: the current graph click/highlight path excludes `run_concurrent` and conflates subflow nodes with ordinary runtime-node matching.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts` is hardcoded to strip a `flowchart-` prefix and treat the remainder as a `junjo.id`.
- Library update tie-in: Junjo’s migration notes explicitly say node/span matching is now:
- normal nodes and run-concurrent nodes: `nodeRuntimeId` <-> `junjo.executable_runtime_id`
- parent-graph subflow nodes: `subflowGraphStructuralId` <-> `junjo.executable_structural_id`
- definition-level subflow matching when needed: parent graph `nodeRuntimeId` <-> `junjo.executable_definition_id`
- E2E data flow touched: parsed execution graph snapshot -> Mermaid graph generation -> DOM IDs -> graph-node lookup -> span lookup -> Redux active span -> routed workflow explorer URL.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`: reimplement Mermaid generation from the current compiled graph snapshot rather than the old generic graph schema.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`: consume the new `workflowExecutionGraphSnapshot` accessor and current graph builder rather than `workflowGraphStructure`.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`: replace “extract Junjo ID” logic with “extract rendered graph node identifier,” and make that identifier resolve through the parsed graph model rather than directly to a span attribute.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`: replace direct `junjoId` lookups with explicit graph-node-to-span matching rules.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`: include `run_concurrent` spans as graph-selectable executables.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`: update subflow highlighting so it uses structural matching for subflow container nodes instead of `workflowChain.some(span => wrapSpan(span).junjoId === nodeId)`.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`: update graph failure annotation to use the new failure classifier from Phase 4 rather than raw `exception.type` event checks.
- Validation gate for this phase: clicking or highlighting every executable type in the current-Junjo fixtures must navigate to the correct span and keep the correct node highlighted.
- Main risk: subflow container rendering and matching is the highest-risk part of the refactor because the rendered node represents a structural relationship, not a simple runtime node span.

## Phase 4: Replace The Legacy “Exceptions” Model With Current Junjo Failure Semantics

- Objective: make failure, exception, hook failure, and cancellation handling match the current library behavior.
- Problem: current UI logic mostly treats “has `exception.type` event” as the definition of failure.
- Problem: failed spans can now be identified by span-level `error.type`, and hook failures now arrive as `junjo.hook_error` events on surrounding spans.
- Problem: ordinary cancellations now carry `junjo.cancelled` and should not be mislabeled as failures.
- Library update tie-in: current Junjo emits:
- `error.type` on failed workflow, subflow, node, and concurrent spans
- standard `exception` event when exception recording happens
- `junjo.hook_error` event for hook callback failures
- `junjo.cancelled` and `junjo.cancelled_reason` for cancellation. `/Users/matt/repos/junjo/docs/opentelemetry.rst:239-249` `/Users/matt/repos/junjo/src/junjo/_lifecycle.py:619-642` `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py:9-22`
- E2E data flow touched: OTLP span attrs/events -> ingestion JSON serialization -> DataFusion `attributes_json/events_json` -> selector classification -> list badges, graph markers, span detail tabs, workflow detail pane.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`: replace `selectTraceExceptionSpans` with a current failure selector that classifies:
- failed executable spans by `attributes_json["error.type"]`
- standard `exception` events
- `junjo.hook_error` events
- cancellations by `attributes_json["junjo.cancelled"]`
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`: add explicit schemas for `junjo.hook_error` and any normalized frontend failure item representation used by selectors.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`: stop using raw `exception.type` event checks and use the new failure classification.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`: stop using raw `exception.type` event checks and use the new failure classification.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`: change workflow alert badges to reflect current failure classification rather than exception-only traces.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`: replace the exception-only tab source with the new failure selector.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`: replace the component or repurpose it into a failure details view that can render:
- standard exceptions
- hook failures
- span-level failure metadata
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`: switch the local exception tab trigger and failure detection from raw event scanning to the new failure model.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`: node red/error annotation must use the same failure selector or shared failure utility, not component-local raw event checks.
- Validation gate for this phase: current-Junjo fixtures must show correct UI behavior for:
- failed node span with `error.type`
- failed workflow span with `error.type`
- hook callback failure recorded as `junjo.hook_error`
- cancelled span with `junjo.cancelled=true`
- Main risk: keeping exception-only labels or selectors will silently hide real failures from the workflow list, graph, and workflow detail tabs.

## Phase 5: Rewrite State And Store Attribution Around Current Junjo Semantics

- Objective: make state timelines and store ownership match the current active-executable model rather than legacy store heuristics.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts` currently reads the wrong workflow store key.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts` hardcodes a legacy rule where a selected subflow defaults to `junjo.workflow.parent_store.id`.
- Problem: Junjo now attributes state changes to the active executable and supplies explicit executable and parent-executable identity fields for reasoning about that relationship. `/Users/matt/repos/junjo/src/junjo/store.py:181-237`
- Library update tie-in: workflow/subflow spans now emit `junjo.workflow.store.id` and subflows also emit `junjo.workflow.parent_store.id`; state changes are attached to the active span and lifecycle payloads carry current executable identity.
- E2E data flow touched: `set_state` event on active span -> ingestion persists event JSON unchanged -> backend returns `events_json` unchanged -> frontend selects events by store and active span/store ownership.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`: replace the stale `workflowStoreId` getter with current `junjo.workflow.store.id` and add an explicit `parentWorkflowStoreId` getter for `junjo.workflow.parent_store.id`.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`: revisit `selectWorkflowSpanByStoreId`, `selectStateEventsByJunjoStoreId`, `selectBeforeSpanStateEventInWorkflow`, and `selectActiveStoreID` so they use the current store keys and the chosen subflow-state product rule.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`: stop treating store ownership as a side effect of legacy subflow logic and instead derive it explicitly from:
- active span type
- selected state event, if any
- active workflow/subflow store id
- parent store id when relevant
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`: update the active workflow/store selection logic to reflect the new accessor and current subflow decision.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/FlatStateEventsList.tsx`: review whether state-event rows should show the owning executable identity or store origin when the trace mixes parent-store and subflow-store mutations.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateNav.tsx`: review and update state navigation labels if the UI now needs to distinguish subflow-owned and parent-store state events.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedWorkflowSpans.tsx`: review whether nested state rows need clearer attribution or labels now that active executable identity is explicit.
- Validation gate for this phase: the current-Junjo fixtures must prove correct behavior for:
- plain workflow state changes
- subflow state changes against the subflow store
- subflow pre-run or post-run state changes against the parent store
- run-concurrent child state changes
- state navigation and diff reconstruction around the selected active span
- Main risk: the state panel can appear plausible while silently diffing the wrong store if store ownership is still driven by legacy assumptions.

## Phase 6: Delivery Cleanup, Integration Polish, And Documentation

- Objective: finish the refactor by updating outward-facing guidance and closing the remaining integration gaps without changing the generic transport layers.
- Problem: `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx` is stale relative to the current Junjo library guidance and should not keep teaching the older exporter setup.
- Problem: the refactor will otherwise leave scattered code comments and component names that still talk about `junjo.id`, “exceptions only,” or old graph payload semantics.
- Library update tie-in: current Junjo docs describe the current exporter setup and current telemetry surface. `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst:342-420` `/Users/matt/repos/junjo/docs/opentelemetry.rst:234-360`
- E2E data flow touched: this phase does not change runtime data flow. It aligns documentation, fixtures, and tests with the refactored current-Junjo frontend interpretation.
- Code change required in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx`: update the example to current Junjo guidance and remove stale assumptions.
- Code change required across the touched frontend files: remove or rewrite comments that still describe `junjo.id`, `junjo.workflow.graph_structure`, or exception-only failure handling.
- Code change required in new frontend tests: add focused coverage for:
- the current `SpanAccessor`
- graph snapshot parsing
- graph node to span matching
- failure classification
- subflow state/store attribution
- Code change required in new backend tests: add transport fidelity tests proving that the current Junjo payload survives hot and cold query paths unchanged.
- Validation gate for this phase: the updated tests and fixtures must cover the current library surface end-to-end, and the remaining unchanged runtime layers must be explicitly documented as unchanged by design.
- Main risk: skipping this cleanup phase leaves the repo with correct code but stale instructions and weak regression coverage, which guarantees future drift.

## Files That Require Code Changes

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/FlatStateEventsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateNav.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedWorkflowSpans.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`
- new current-Junjo fixtures and tests in backend and frontend test locations

## Files That Must Be Reviewed But Should Likely Stay Unchanged

- `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/trace_service.rs`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/schema.rs`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/arrow_wal.rs`
- `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/internal_service.rs`
- `/Users/matt/repos/junjo-ai-studio/proto/ingestion.proto`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/span_ingestion/ingestion_client.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/repository.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/router.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/features/parquet_indexer/parquet_reader.py`
- `/Users/matt/repos/junjo-ai-studio/backend/app/db_sqlite/metadata/indexer.py`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/fetch/get-trace-spans.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/fetch/get-spans-type-workflow.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/span-name-constructor.ts`

## Recommended Execution Order

- Start with Phase 0 and do not skip it.
- Implement Phase 1 before touching graph rendering components.
- Implement Phase 2 before Phase 3 so graph rendering uses a correct view model.
- Implement Phase 4 before polishing graph error markers and workflow badges so all failure surfaces use one classification model.
- Implement Phase 5 only after Phase 1 is complete, because the new accessor and current store keys are prerequisites.
- Finish with Phase 6 so tests, fixtures, and exporter guidance match the refactored codebase.

## Definition Of Done For This Refactor

- OTLP ingestion, hot snapshot querying, cold Parquet querying, and REST delivery remain generic and unchanged by design.
- The frontend no longer reads `junjo.id`, `junjo.parent_id`, `junjo.workflow.graph_structure`, or `junjo.workflow.store_id`.
- The frontend graph model parses `junjo.workflow.execution_graph_snapshot` exactly as current Junjo emits it.
- Mermaid rendering and node/span matching follow Junjo’s runtime and structural matching rules.
- Workflow list badges, graph markers, trace lists, and detail panes surface `error.type`, standard exceptions, hook failures, and cancellations correctly.
- State/store views use the current workflow and subflow store fields and the chosen subflow-state product rule.
- The repo contains current-Junjo fixtures and tests that protect the transport boundary and the frontend interpretation layer.
