# Phase 1 Plan

## Purpose

- This document defines the concrete work required to complete Phase 1 of the Junjo library update refactor in `junjo-ai-studio`.
- Phase 1 is the frontend Junjo domain-contract rewrite phase.
- It exists to replace AI Studio’s stale Junjo interpretation layer after Phase 0 proved that the end-to-end OTLP transport path is already preserving the current Junjo payload correctly.
- This is a greenfield refactor.
- No backward compatibility, fallbacks, shims, adapters, migrations, or dual-schema support are in scope.
- The target state is current Junjo only.

## Why Phase 1 Exists

- Phase 0 established that the ingestion service, WAL/Parquet persistence, internal gRPC, backend DataFusion query path, and REST delivery are generic OTEL transport layers and do not require Junjo-specific runtime refactors.
- That means the first real runtime break is in the frontend code that interprets `attributes_json` and `events_json`.
- Today the frontend still assumes removed Junjo keys and an old graph payload:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- `junjo.workflow.store_id`
- current Mermaid graph correlation also assumes rendered node IDs can map directly to `junjo.id`

- The Junjo library now emits a different frontend contract:
- explicit executable identity fields
- explicit parent executable identity fields
- enclosing graph structural identity
- `junjo.workflow.execution_graph_snapshot`
- `junjo.workflow.store.id`
- `junjo.workflow.parent_store.id`
- span-level `error.type`
- `junjo.hook_error` events on the containing span

- Phase 1 fixes the frontend contract layer before the graph rendering/correlation rewrite.
- If this phase is skipped, later graph and UI work will keep rebuilding on stale `SpanAccessor` assumptions and will remain brittle even if the graph parser is updated.

## Scope Boundary

- In scope:
- current-Junjo frontend parsing and typed access
- current-Junjo event and failure classification helpers
- selector migration to current keys
- workflow/state/detail consumers that rely on the typed span contract
- current execution graph snapshot parsing ownership, if needed as a typed schema owner
- tests for the new frontend Junjo contract

- Out of scope:
- Mermaid rendering rewrite
- graph-node-to-span correlation rewrite
- DOM ID mapping changes
- graph structural/runtime highlighting logic
- backend runtime changes
- ingestion runtime changes
- transport-layer schema changes
- product redesign of subflow store and parent store views

- User decisions locked for this phase:
- hook failures should show as normal span failures
- subflow store and parent store state views should have no product changes or extra consideration in this phase

## Source Of Truth

- Junjo migration notes:
- `/Users/matt/repos/junjo/AI_STUDIO_MIGRATION_NOTES.md`

- Junjo docs:
- `/Users/matt/repos/junjo/docs/junjo_ai_studio.rst`
- `/Users/matt/repos/junjo/docs/opentelemetry.rst`

- Junjo runtime emission:
- `/Users/matt/repos/junjo/src/junjo/workflow.py`
- `/Users/matt/repos/junjo/src/junjo/node.py`
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`
- `/Users/matt/repos/junjo/src/junjo/store.py`
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`
- `/Users/matt/repos/junjo/src/junjo/graph.py`
- `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py`

- AI Studio frontend surfaces investigated for this phase:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`

## Phase 0 Baseline

- Phase 0 is complete.
- The shared current-Junjo fixture corpus now lives at:
- `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update/`

- The transport contract is now locked by:
- ingestion serialization tests
- backend DataFusion hot/cold/fused query tests
- backend OTLP ingestion integration tests
- frontend generic OTEL payload parse tests

- Architectural conclusion carried into Phase 1:
- `attributes_json` and `events_json` are already the correct transport boundary
- the problem is not “data not arriving”
- the problem is “frontend Junjo code interprets the wrong keys and wrong shape”

## Confirmed Current Junjo Contract Relevant To Phase 1

- Confirmed executable identity fields on workflow/subflow spans:
- `junjo.executable_definition_id`
- `junjo.executable_runtime_id`
- `junjo.executable_structural_id`
- `junjo.parent_executable_definition_id`
- `junjo.parent_executable_runtime_id`
- `junjo.parent_executable_structural_id`
- `junjo.enclosing_graph_structural_id`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`

- Confirmed executable identity fields on node spans:
- `junjo.executable_definition_id`
- `junjo.executable_runtime_id`
- `junjo.executable_structural_id`
- `junjo.parent_executable_definition_id`
- `junjo.parent_executable_runtime_id`
- `junjo.parent_executable_structural_id`
- `junjo.enclosing_graph_structural_id`
- `/Users/matt/repos/junjo/src/junjo/node.py`

- Confirmed executable identity fields on run-concurrent spans:
- `junjo.span_type = "run_concurrent"`
- same explicit executable identity pattern as nodes
- `/Users/matt/repos/junjo/src/junjo/run_concurrent.py`

- Confirmed workflow graph payload:
- `junjo.workflow.execution_graph_snapshot`
- stored as a JSON string attribute
- not `junjo.workflow.graph_structure`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`
- `/Users/matt/repos/junjo/src/junjo/graph.py`

- Confirmed workflow store fields:
- `junjo.workflow.store.id`
- `junjo.workflow.parent_store.id`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`

- Confirmed workflow state fields:
- `junjo.workflow.state.start`
- `junjo.workflow.state.end`
- `/Users/matt/repos/junjo/src/junjo/workflow.py`
- `/Users/matt/repos/junjo/docs/opentelemetry.rst`

- Confirmed failure signals:
- failed executable spans use span-level `error.type`
- cancellations use `junjo.cancelled` and `junjo.cancelled_reason`
- hook callback failures are `junjo.hook_error` events on the containing span
- standard `exception` events may still also be present
- `/Users/matt/repos/junjo/src/junjo/telemetry/span_lifecycle.py`
- `/Users/matt/repos/junjo/src/junjo/_lifecycle.py`

## Main Problems Phase 1 Must Solve

### Problem 1: The typed Junjo accessor is stale

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts` still centralizes removed keys.
- That makes every consumer of `wrapSpan(span)` wrong by construction.
- This file is the highest-leverage frontend refactor point because it is the current single owner of Junjo attribute names.

### Problem 2: The frontend has no current Junjo domain schema owner

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts` keeps `OtelSpanSchema` generic, which is correct.
- But it only adds narrow Junjo helper schemas for:
- `set_state`
- `exception`

- It does not provide typed parsing for:
- `junjo.hook_error`
- span-level failure attributes
- current execution graph snapshots
- explicit executable identity semantics

- That leaves selectors and components to re-derive the contract ad hoc.

### Problem 3: Selectors still encode legacy Junjo assumptions

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts` still:
- looks up workflow ownership by the stale store key
- classifies failures by exception events only
- uses raw active-span/subflow logic built on the old accessor contract

- These selectors are the bridge between transport data and UI behavior.
- If they stay stale, updating only UI components will not fix the product behavior.

### Problem 4: Failure handling is narrower than the current Junjo model

- The UI currently interprets “span has exception event” as “span failed.”
- That is now incomplete.
- Current Junjo failure needs to treat hook failures as normal span failures and include `error.type` at the span attribute level.

- Affected visible surfaces:
- workflow list warning badges
- span row badges
- nested span badges
- exceptions/failures tab visibility
- workflow detail failure content
- graph node error markers later

### Problem 5: State/store consumers read stale keys

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`

- These surfaces still depend on `workflowStoreId` coming from the stale accessor implementation.
- This phase does not redesign subflow vs parent store behavior.
- It does need to make current keys the only supported keys.

### Problem 6: Graph consumers are downstream of the stale contract

- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`

- Phase 1 does not need to solve rendering or correlation.
- It does need to stop perpetuating the old `junjoId`/old graph shape contract and define the new execution-snapshot ownership boundary cleanly for the next phase.

## Surface Area Inventory

### Primary Refactor Owner Files

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- recommended new schema owner file for execution graph snapshots under:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/`
- or
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/`

### Selector And State Consumers

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`

### Failure/Badge/List Consumers

- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx`

### Graph Consumers Affected By The Contract Rewrite

- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`

### Coverage Gap

- There are currently no dedicated frontend unit tests for:
- `wrapSpan`
- Junjo selector behavior
- current failure classification
- current graph snapshot parsing

- That means Phase 1 must add its own coverage; otherwise this contract layer remains unprotected.

## Strategy

- Keep `OtelSpanSchema` generic.
- Add a single current-Junjo domain layer on top of it.
- Make that layer the only owner of current Junjo field names and parsing rules.
- Migrate selectors to depend on that layer.
- Migrate non-graph UI consumers to depend on selector/domain helpers rather than raw attribute scanning.
- Prepare the graph boundary for the next phase, but do not mix the graph rendering rewrite into this phase.

## Phase 1 Internal Subphases

### Phase 1A: Define The Current Junjo Domain Contract

- Goal:
- replace stale Junjo accessor semantics with current executable identity, store, graph snapshot, and failure fields

- Problems solved:
- stale key constants
- stale getter names
- duplicated raw attribute access in selectors/components

- Required work:
- rewrite `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`
- replace old key constants:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- `junjo.workflow.store_id`

- with current-only keys:
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
- `junjo.workflow.state.start`
- `junjo.workflow.state.end`
- `error.type`
- `junjo.cancelled`
- `junjo.cancelled_reason`

- New target-state accessor surface should include:
- `spanType`
- `isWorkflow`
- `isSubflow`
- `isNode`
- `isRunConcurrent`
- `isJunjoSpan`
- `executableDefinitionId`
- `executableRuntimeId`
- `executableStructuralId`
- `parentExecutableDefinitionId`
- `parentExecutableRuntimeId`
- `parentExecutableStructuralId`
- `enclosingGraphStructuralId`
- `workflowExecutionGraphSnapshot`
- `workflowStoreId`
- `workflowParentStoreId`
- `workflowStateStart`
- `workflowStateEnd`
- `errorType`
- `isCancelled`
- `cancelledReason`
- `exceptionEvents`
- `hookErrorEvents`
- `hasFailureSignal`

- Explicit removals from the target-state API:
- `junjoId`
- `junjoParentId`
- `workflowGraphStructure`
- any getter that still implies old one-ID semantics

- Validation:
- add unit tests for the accessor using the shared Phase 0 fixture corpus

### Phase 1B: Add Current-Junjo Typed Schemas

- Goal:
- stop leaving current Junjo parsing spread across selectors and UI code

- Problems solved:
- no schema for `junjo.hook_error`
- no schema for current graph snapshot
- no normalized failure helper types

- Required work:
- update `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`
- preserve the generic `OtelSpanSchema`
- add new helper schemas for:
- `junjo.hook_error`
- standard `exception`
- `set_state`
- any small failure summary shape used by selectors

- Add a current execution graph snapshot schema owner:
- recommended location:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- or a new file under:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/`

- This schema should represent the current Junjo payload, not the old graph shape:
- `graphStructuralId`
- `nodeRuntimeId`
- `nodeStructuralId`
- `nodeType`
- `nodeLabel`
- `isConcurrentSubgraph`
- `childNodeRuntimeIds`
- `isSubflow`
- `subflowGraphStructuralId`
- `subflowSourceNodeRuntimeId`
- `subflowSourceNodeStructuralId`
- `subflowSinkNodeRuntimeIds`
- `subflowSinkNodeStructuralIds`
- `edgeStructuralId`
- `tailNodeRuntimeId`
- `tailNodeStructuralId`
- `headNodeRuntimeId`
- `headNodeStructuralId`
- `edgeConditionLabel`
- `edgeScope`
- `parentSubflowRuntimeId`

- Validation:
- fixture-driven parse tests for the new schema owners

### Phase 1C: Rewrite Selector Semantics Around The New Contract

- Goal:
- migrate selector behavior to the current domain layer

- Problems solved:
- stale store lookup
- exception-only failure selection
- selectors reading raw attributes instead of a single owner

- Required work in `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`:
- replace `wrapSpan(span).junjoSpanType` usage with the new accessor surface if naming changes
- replace `workflowStoreId` lookup to read `junjo.workflow.store.id`
- keep current store-view behavior, but remove stale key assumptions
- replace `selectTraceExceptionSpans` with a broader failure selector or rename it to reflect the current behavior

- Failure selector must treat these as span failures:
- span `error.type`
- standard `exception` events
- `junjo.hook_error` events

- Failure selector must not treat these as failures:
- plain `junjo.cancelled` without failure signals

- Store/state selectors to touch:
- `selectWorkflowSpanByStoreId`
- `selectStateEventsByJunjoStoreId`
- `selectBeforeSpanStateEventInWorkflow`
- `selectActiveStoreID`

- Current product constraint:
- do not redesign subflow/parent-store state behavior here
- only make existing behavior run on current keys

- Validation:
- selector tests using the Phase 0 fixtures

### Phase 1D: Migrate Non-Graph UI Consumers

- Goal:
- make visible workflow/span/detail behavior consume the new contract

- Problems solved:
- raw exception scanning in components
- stale assumptions leaking through UI rather than selectors

- Required work:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx`

- Required outcome:
- hook failures render as normal span failures
- failure badges/tabs are not limited to exception events
- state panel still works using current workflow store keys
- Junjo span-type icons continue to work through the new accessor

- Recommended naming cleanup:
- if the UI still uses “exceptions” labels in this phase, the underlying selector and behavior should still be failure-aware
- if time permits, rename exception-only surfaces to failure-oriented names in the same phase

### Phase 1E: Prepare The Graph Boundary Without Doing The Graph Rewrite

- Goal:
- stop carrying the old graph contract forward

- Problems solved:
- `workflowGraphStructure` is the wrong conceptual API
- graph consumers still expect old graph schema ownership

- Required work:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`
- update this component to consume the new `workflowExecutionGraphSnapshot` owner name if that accessor changes

- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`
- define current execution graph snapshot ownership

- `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`
- evaluate whether this file should remain untouched until Phase 2 or whether a minimal rename/prep change is needed now

- Explicitly defer:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`
- `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/mermaid-render-utils.ts`
- full graph-node correlation rewrite

- Rule:
- Phase 1 may rename or re-point graph snapshot ownership
- Phase 1 must not try to solve runtime/structural correlation

### Phase 1F: Add Coverage For The New Frontend Contract

- Goal:
- make the new domain layer hard to regress

- Problems solved:
- no frontend tests for this contract layer today

- Required work:
- add accessor tests
- add selector tests
- add failure-classification tests
- add graph snapshot parse tests if the schema owner is introduced in this phase

- Test inputs should come from:
- `/Users/matt/repos/junjo-ai-studio/test-fixtures/junjo-library-update/`

- Minimum fixture scenarios to cover:
- basic workflow
- subflow
- run-concurrent
- failed span with `error.type`
- cancelled span
- hook failure on containing span

## Detailed Surface Area By File

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/utils/span-accessor.ts`

- confirmed stale keys
- confirmed stale getter names
- this is the main owner that must be replaced first

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/schemas.ts`

- still generic at the top level, which is good
- narrow helper coverage only
- needs current-Junjo helper schemas

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/store/selectors.ts`

- uses stale `workflowStoreId`
- exception-only selector behavior
- state/store behavior depends on the accessor
- this is the largest consumer of `wrapSpan`

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/SpanRow.tsx`

- uses raw exception event checks for the badge
- uses `wrapSpan(span).isWorkflow` for the workflow explorer link

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/NestedSpanRow.tsx`

- uses raw exception checks
- relies on `isJunjoSpan`

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/list-spans-workflow/WorkflowListItem.tsx`

- workflow list warning icon is driven by `selectTraceExceptionSpans`
- this must become failure-aware

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/TabbedSpanLists.tsx`

- exceptions tab visibility uses `selectTraceExceptionSpans`
- this is a direct downstream consumer of failure selector semantics

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/SpanExceptionsList.tsx`

- exception-only rendering
- raw event scanning
- should become failure-aware for hook failures

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/workflow-detail/WorkflowDetailStateDiff.tsx`

- uses `workflowStateStart`
- uses store selectors that depend on stale accessor semantics
- open exceptions tab logic is downstream of failure classification

### `/Users/matt/repos/junjo-ai-studio/frontend/src/features/junjo-data/span-lists/determine-span-icon.tsx`

- lower risk
- still depends on span type helpers staying correct

### `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphList.tsx`

- directly uses `workflowGraphStructure`
- must not keep old naming/ownership once the new contract lands

### `/Users/matt/repos/junjo-ai-studio/frontend/src/mermaidjs/RenderJunjoGraphMermaid.tsx`

- heavy old-ID dependency
- not a Phase 1 implementation target, but must be called out as blocked on the next phase

### `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/schemas.ts`

- still old graph shape
- Phase 1 should define whether this file becomes the current graph snapshot owner

### `/Users/matt/repos/junjo-ai-studio/frontend/src/junjo-graph/junjo-graph.ts`

- still old graph model and old rendering assumptions
- not the main target of this phase, but Phase 1 must not deepen its stale contract coupling

## Recommended Order

- first: Phase 1A
- second: Phase 1B
- third: Phase 1C
- fourth: Phase 1D
- fifth: Phase 1E
- sixth: Phase 1F

- Practical sequencing note:
- tests for the accessor and schemas should start landing as soon as 1A and 1B are in place rather than waiting until the end

## Validation Plan

- Add frontend unit tests for:
- accessor getters using current fixtures
- failure classification behavior
- store selector behavior on current keys
- graph snapshot parse behavior if introduced in this phase

- Keep existing Phase 0 gate:
- `/Users/matt/repos/junjo-ai-studio/frontend/src/features/traces/schemas/junjo-transport-contract.test.ts`

- Minimum verification commands after implementation:
- `cd /Users/matt/repos/junjo-ai-studio/frontend && npm run test:run`
- `cd /Users/matt/repos/junjo-ai-studio/frontend && npm run lint`
- `cd /Users/matt/repos/junjo-ai-studio/frontend && npm run build`

## Non-Goals

- Do not implement graph correlation in this phase.
- Do not implement Mermaid DOM ID mapping changes in this phase.
- Do not rewrite the backend or ingestion layers.
- Do not add backward compatibility for old Junjo keys.
- Do not redesign state/store UX for subflow or parent store views.

## Exit Criteria

- No frontend Junjo domain code reads:
- `junjo.id`
- `junjo.parent_id`
- `junjo.workflow.graph_structure`
- `junjo.workflow.store_id`

- The frontend has one current-Junjo domain owner for:
- executable identity
- store identity
- workflow execution graph snapshot
- failure signals

- Hook failures are treated as normal span failures in the frontend domain layer.
- State/store selectors run on current workflow store keys.
- Main non-graph consumers use the new contract rather than raw attribute/event scanning.
- New frontend tests cover the contract layer.
- The remaining graph-rendering work is clearly isolated to the next phase.

## Main Risks

- The biggest risk is letting Phase 1 sprawl into the full graph rewrite.
- The second biggest risk is updating only the accessor without migrating selectors, which would leave stale behavior behind a new type layer.
- The third biggest risk is keeping exception-only naming and logic in selectors, which would continue to hide hook failures and `error.type` failures even after the accessor is corrected.

## Summary

- Phase 1 is not the graph rewrite.
- Phase 1 is the frontend Junjo contract rewrite that everything else needs first.
- If it is done cleanly, the next phase can focus entirely on compiled graph parsing, Mermaid rendering, and graph-to-span matching without also fighting stale domain semantics.
