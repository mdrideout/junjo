# Library Update Refactor Plan

## Scope

- Goal: refactor Junjo AI Studio to support the current Junjo library only.
- Constraint: greenfield target state only. No backward compatibility, shims, migrations, adapters, or dual-schema support.
- Primary Junjo sources of truth:
- `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md`
- `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst`
- `/Users/matt/repos/junjo/docs/opentelemetry.rst`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`
- `/Users/matt/repos/junjo/src/junjo/store.py`
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`
- `/Users/matt/repos/junjo/src/junjo/node.py`
- `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py`

## Current Status Snapshot

- Working branch: `hardening-compatibility`
- Key implementation commits:
- `e561b5b` `Add Junjo update planning and Phase 0 contract tests`
- `da8b22a` `Refactor frontend Junjo contract for current library`
- `73b9a91` `Fix subflow Mermaid graph span matching`
- Current high-level conclusion:
- The transport path is already compatible with the current Junjo library because ingestion, storage, hot/cold query, and REST delivery are generic OTEL transport.
- The compatibility work was primarily a frontend interpretation refactor.
- The workflow explorer path is now implemented against the current Junjo contract and should be ready for real browser testing with live traces.
- Remaining work is now hardening and cleanup, not core library compatibility implementation.

## End-To-End Contract Baseline

- OTLP ingress starts in `/Users/matt/repos/junjo-ai-studio/ingestion/src/server/trace_service.rs`.
- The ingestion service converts OTLP spans into `SpanRecord` rows and serializes attributes and events as opaque JSON. It does not normalize Junjo keys. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`
- WAL and Parquet persistence use a generic OTEL schema with JSON `attributes`, `events`, and `resource_attributes`. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/schema.rs`
- Hot snapshots and cold flushes preserve the same generic schema. `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/arrow_wal.rs`
- Internal gRPC sends snapshot file paths and recent cold file paths, not Junjo-normalized payloads. `/Users/matt/repos/junjo-ai-studio/proto/ingestion.proto` `/Users/matt/repos/junjo-ai-studio/backend/app/features/span_ingestion/ingestion_client.py`
- Backend DataFusion queries parse JSON back into `attributes_json` and `events_json` and still do not interpret Junjo identity fields. `/Users/matt/repos/junjo-ai-studio/backend/app/features/otel_spans/datafusion_query.py`
- The frontend fetch layer still consumes a generic OTEL API shape through `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`.
- Conclusion:
- No runtime ingestion, storage, gRPC, backend query, or REST contract rewrite is required for the current Junjo library.
- The Junjo-specific break began at the frontend span accessor, graph parser, matching logic, and failure/state interpretation layers.

## Confirmed Junjo Changes Driving The Refactor

- `junjo.id` was replaced by `junjo.executable_runtime_id`.
- `junjo.parent_id` was replaced by `junjo.parent_executable_runtime_id`.
- `junjo.definition_id` was replaced by `junjo.executable_definition_id`.
- `junjo.parent_definition_id` was replaced by `junjo.parent_executable_definition_id`.
- `junjo.workflow.graph_structure` was replaced by `junjo.workflow.execution_graph_snapshot`.
- Workflow and subflow spans now emit explicit executable runtime, definition, structural, parent-executable, enclosing-graph, and store fields.
- The execution graph snapshot now uses compiled graph identity fields such as:
- `graphStructuralId`
- `nodeRuntimeId`
- `nodeStructuralId`
- `edgeStructuralId`
- `tailNodeRuntimeId`
- `headNodeRuntimeId`
- subflow structural linkage fields
- run-concurrent child linkage fields
- Mermaid/span correlation is no longer direct `junjo.id` matching:
- normal nodes and `run_concurrent` correlate by runtime identity
- parent-graph subflow container nodes correlate by subflow structural identity
- failed spans now use span-level `error.type`
- hook failures now arrive as `junjo.hook_error` events on the containing span
- state events remain `set_state` events on the active span
- trace ancestry still uses OTEL `parent_span_id`, not Junjo parent executable fields

## Phase-By-Phase Validation

## Phase 0: Lock The Transport Contract Before Refactoring

- Status: validated complete
- Implemented in: `e561b5b`
- Original problem:
- The plan needed to prove what the current Junjo payload looked like after OTLP ingestion, WAL/Parquet persistence, hot/cold querying, and backend delivery.
- Without that contract lock, the frontend refactor would have been based on guessed payloads.
- Current codebase validation:
- Shared current-Junjo fixtures exist at `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update`.
- Fixture scenarios cover:
- `basic_workflow_success.json`
- `subflow_with_parent_store.json`
- `run_concurrent_success.json`
- `failed_executable_with_error_type.json`
- `cancelled_executable.json`
- `hook_failure_on_surrounding_span.json`
- Fixture ownership is documented in `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update/README.md`.
- Backend fixture loading and builders exist in:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_fixture_loader.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_transport_builders.py`
- Frontend fixture loading exists in:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/test-utils/junjo-fixture-loader.ts`
- Rust ingestion serialization coverage exists in `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`.
- That coverage explicitly verifies:
- `junjo.workflow.execution_graph_snapshot`
- `junjo.executable_runtime_id`
- `junjo.executable_structural_id`
- `error.type`
- `junjo.cancelled`
- `set_state`
- `junjo.hook_error`
- Backend hot/cold/fused contract tests exist in:
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_junjo_transport_contract_integration.py`
- Frontend transport parsing is locked by `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/junjo-transport-contract.test.ts`.
- Revised plan for this phase:
- No further Phase 0 implementation work is planned.
- Phase 0 is now serving its intended purpose as regression protection for the transport boundary.
- Remaining work tied to this phase:
- None, unless Junjo changes the transport-visible payload again.

## Phase 1: Rewrite The Frontend Junjo Domain Contract

- Status: validated complete
- Implemented in: `da8b22a`
- Original problem:
- The frontend Junjo access layer still read removed keys such as `junjo.id`, `junjo.parent_id`, `junjo.workflow.graph_structure`, and stale `junjo.workflow.store_id`.
- Failure classification was also stale because it leaned on exception events instead of current Junjo failure signals.
- Current codebase validation:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts` now reads current Junjo fields only:
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
- The accessor now exposes:
- executable identity helpers
- store helpers
- parsed execution snapshot access
- parsed exception and hook failure events
- unified `hasFailureSignal`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts` now defines:
- generic OTEL span/event schemas
- `JunjoSetStateEventSchema`
- `JunjoExceptionEventSchema`
- `JunjoHookErrorEventSchema`
- Accessor coverage exists in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.test.ts`.
- That coverage verifies:
- workflow executable identity parsing
- subflow parent-store metadata
- run-concurrent identity parsing
- failure handling for `error.type`
- hook failure handling for `junjo.hook_error`
- cancellation remaining non-failure
- Revised plan for this phase:
- No additional Phase 1 implementation is planned.
- The current-Junjo span contract is now the active owner of frontend Junjo interpretation.
- Remaining work tied to this phase:
- None, outside normal regression maintenance.

## Phase 2: Replace The Execution Graph Snapshot Schema And View Model

- Status: validated complete
- Implemented in: `da8b22a`
- Original problem:
- The frontend graph schema still assumed the removed payload shape with generic node IDs, generic edges, and legacy subflow fields.
- Current codebase validation:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts` now matches the current execution snapshot shape:
- `graphStructuralId`
- current node runtime and structural IDs
- current edge runtime and structural IDs
- subflow fields
- run-concurrent child-node fields
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts` now builds Mermaid from the current compiled graph payload instead of the removed graph schema.
- The graph builder explicitly handles:
- top-level executable nodes
- `run_concurrent` container subgraphs
- subflow container nodes
- omission of subflow-internal edges from parent workflow Mermaid output
- Graph parsing and rendering coverage exists in `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.test.ts`.
- Revised plan for this phase:
- No additional Phase 2 implementation is planned.
- The graph snapshot model now matches the current Junjo payload for the workflow explorer path.
- Remaining work tied to this phase:
- None, outside any future Junjo graph payload change.

## Phase 3: Rebuild Mermaid Rendering And Graph-To-Span Correlation

- Status: validated complete for the workflow explorer path
- Implemented in: `da8b22a`, `73b9a91`
- Original problem:
- Mermaid rendering assumed rendered node IDs could map directly to the removed `junjo.id`.
- Subflows and `run_concurrent` needed different matching logic under the current Junjo model.
- The original Phase 1 implementation still had one real gap: subflow container matching in the parent graph.
- Current codebase validation:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx` now consumes `workflowExecutionGraphSnapshot`.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx` now:
- extracts rendered graph node IDs
- resolves them through the parsed graph snapshot
- navigates to spans through explicit graph-node matching logic
- includes `run_concurrent` spans in graph interaction
- annotates failed nodes using the unified failure signal
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts` now only extracts rendered graph node IDs, not fake Junjo IDs.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/junjo-graph-span-matching.ts` now implements the current matching rules:
- normal nodes and `run_concurrent` by executable runtime ID
- subflow container nodes by `subflowGraphStructuralId` to span structural ID
- definition fallback for subflow node lookup where needed
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/junjo-graph-span-matching.test.ts` covers:
- normal node mapping
- run-concurrent mapping
- parent-graph subflow structural mapping
- Revised plan for this phase:
- No further Phase 3 implementation is planned for the workflow explorer surface.
- The earlier subflow gap is closed by `73b9a91`.
- Remaining work tied to this phase:
- Manual browser verification with real traces remains useful, but there is no open planned code refactor in this phase.

## Phase 4: Replace The Legacy Exceptions Model With Current Failure Semantics

- Status: validated complete for the workflow explorer path
- Implemented in: `da8b22a`
- Original problem:
- Failure surfaces were biased toward exception events and missed current Junjo failure signals.
- Hook failures were invisible because they are no longer standalone spans.
- Current codebase validation:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts` now exposes `selectTraceFailureSpans`, which filters via `wrapSpan(span).hasFailureSignal`.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts` defines `hasFailureSignal` as:
- `error.type`
- exception events
- hook error events
- not cancellation
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanFailuresList.tsx` replaced the old exception-only detail component and renders:
- exception details
- hook failure details
- span-level failure metadata
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx` now shows a failures tab.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx` now uses failure classification for workflow badges.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx` now routes to the failures tab using the unified failure model.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx` marks graph nodes with failure styling based on the same unified failure model.
- Selector coverage exists in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.test.ts`.
- That coverage verifies:
- `error.type` failure selection
- hook failure selection
- cancellations excluded from failures
- Revised plan for this phase:
- No additional Phase 4 implementation is planned for the workflow explorer path.
- The user-directed product decision is implemented: hook failures show as normal span failures.
- Remaining work tied to this phase:
- None, outside manual QA and normal regression coverage.

## Phase 5: State And Store Attribution Under Current Junjo Fields

- Status: validated complete for the current scope of this refactor
- Implemented in: `da8b22a`, plus subsequent store-default adjustment on `hardening-compatibility`
- Original problem:
- Store selection and state diff logic used stale Junjo keys.
- The original plan also assumed there might need to be a product decision around subflow store vs parent store views.
- Revised product decision:
- When a workflow or subflow span is selected with no specific state event selected, the default state view should use that executable's own `junjo.workflow.store.id`.
- When a specific state event is selected, the state view should switch to the store named by that event's `junjo.store.id`.
- `junjo.workflow.parent_store.id` remains useful metadata for understanding subflow relationships, but it is no longer the default subflow state view.
- Current codebase validation:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts` now exposes:
- `workflowStoreId`
- `workflowParentStoreId`
- current workflow state start/end parsing
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts` now uses current keys for:
- `selectWorkflowSpanByStoreId`
- `selectStateEventsByJunjoStoreId`
- `selectBeforeSpanStateEventInWorkflow`
- `selectActiveStoreID`
- `selectActiveStoreID` now defaults selected subflows to the subflow store and only overrides to another store when a selected state event names that store.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx` now consumes the current-key selectors and store accessors.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateNav.tsx` and `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowStateDiffNavButtons.tsx` still drive the existing state-event navigation flow.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/FlatStateEventsList.tsx` and `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedWorkflowSpans.tsx` still operate on `set_state` events with the current event schema.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.test.ts` verifies:
- state events selected by `junjo.store.id`
- workflow span selection by current store IDs
- subflow selection defaulting to the subflow store
- selected state events overriding the default store
- Revised plan for this phase:
- No additional Phase 5 implementation is planned unless live testing reveals a real bug.
- This phase now includes the subflow default-store correction so the UX matches the executable the user selected while still following the selected state event when one is active.
- Remaining work tied to this phase:
- Live validation with richer traces is still useful, but that is now a Phase 6 hardening task, not an open Phase 5 refactor.

## Phase 6: Hardening, Manual QA, And Cleanup

- Status: remaining
- Original problem:
- After the compatibility refactor landed, the repo still needed live validation and cleanup so the branch would not stop at fixture-only confidence.
- Current codebase validation:
- Core automated coverage now exists for:
- transport fidelity
- current span accessor behavior
- selector failure/store behavior
- graph snapshot parsing
- graph/span correlation
- The main remaining gap is live browser validation with real current-Junjo traces through the actual workflow detail UX.
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx` still appears stale relative to the current Junjo docs and examples.
- There is still at least one stale comment in `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx` referring to “graph structure” generically, even though the implementation is now execution-snapshot based.
- Revised plan for this phase:
- This is now the only active phase in the library update plan.
- It should focus on validation and cleanup, not new architecture.
- Concrete remaining work:
- Run a real browser smoke test with live current-Junjo traces through:
- ingestion
- workflow list
- workflow detail page
- Mermaid graph click/highlight behavior
- state navigation
- failures tab
- Validate live traces for:
- basic workflow
- subflow
- run_concurrent
- failure with `error.type`
- hook failure with `junjo.hook_error`
- cancellation
- mixed state-event traces
- Update `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx` so it reflects the current Junjo exporter guidance.
- Clean up any stale comments or labels that still describe removed graph/failure concepts.
- Add any missing regression tests only if live QA exposes a real gap not covered by the current fixture set.
- Exit criteria:
- The browser workflow explorer behaves correctly with live current-Junjo traces.
- The exporter/setup guidance is current.
- No known stale compatibility guidance remains in the touched surfaces.

## Files With Meaningful Refactor Changes Already Landed

- `/Users/matt/repos/junjo-ai-studio/ingestion/src/wal/span_record.rs`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_fixture_loader.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/helpers/junjo_transport_builders.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_datafusion_query.py`
- `/Users/matt/repos/junjo-ai-studio/backend/tests/test_junjo_transport_contract_integration.py`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/junjo-transport-contract.test.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.test.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.test.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.test.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/junjo-graph-span-matching.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/junjo-graph-span-matching.test.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanFailuresList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateNav.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowStateDiffNavButtons.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/FlatStateEventsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedWorkflowSpans.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`

## Files Still Expected To Change

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/api-keys/components/OtelExporterGuide.tsx`
- Any touched frontend file where live QA exposes a real workflow explorer bug not covered by the existing fixture set

## Files Reviewed And Confirmed As Generic Transport Layers

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

## Revised Execution Order

- Completed:
- Phase 0
- Phase 1
- Phase 2
- Phase 3
- Phase 4
- Phase 5
- Remaining:
- Phase 6

## Definition Of Done

- The transport stack remains generic by design:
- OTLP ingestion
- WAL/Parquet persistence
- internal gRPC
- hot/cold DataFusion querying
- REST delivery
- The frontend no longer depends on removed Junjo keys such as:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- `junjo.workflow.store_id`
- The workflow explorer path uses:
- `junjo.workflow.execution_graph_snapshot`
- current executable identity fields
- current graph/span matching rules
- current failure signals
- current store keys
- Current-Junjo fixtures and tests protect the transport boundary and the frontend interpretation layer.
- Manual browser validation with live traces has been completed and any issues found during that pass have been resolved.
- The exporter/setup guidance matches the current Junjo library.
