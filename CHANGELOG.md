# Changelog

All notable changes to Junjo will be documented in this file.

## FUTURE RELEASE

This release is a runtime hardening and API cleanup pass across workflow
execution, state management, and lifecycle observation.

### Highlights

- Hardened workflow and subflow execution so a single definition object can be reused safely across concurrent runs.
- Standardized `Workflow.execute()` around `ExecutionResult`, making final state access explicit and run-scoped.
- Hardened store reads and writes so state snapshots are detached and committed updates are validated atomically against the current locked state.
- Replaced the old telemetry-shaped hook system with a greenfield lifecycle hooks API built around typed events and separated from OpenTelemetry internals.
- Changed `RunConcurrent` to fail fast, cancel pending siblings, and record cancellation telemetry for cancelled branches.

### Breaking Changes

- `Workflow.execute()` now returns an `ExecutionResult` and workflow-instance state access is no longer the post-run access pattern.
- Removed blueprint-style workflow state access from workflow definitions in favor of result-based access.
- Replaced `HookManager` and its related telemetry hook schema with the new `Hooks` lifecycle API.
- Renamed workflow constructor hook wiring from `hook_manager=` to `hooks=`.
- Removed `BaseStore.subscribe()` and the old subscriber implementation.
- Subflow hook implementations now work with explicit `subflow_store` access in `pre_run_actions` and `post_run_actions`.
- `Graph` now requires `sinks=[...]` instead of `sink=...`.

### Added

- Added `ExecutionResult` as the public completion snapshot for workflows and subflows.
- Added a public `Hooks` API with typed lifecycle events for workflows, subflows, nodes, concurrent execution, and state changes.
- Added an internal lifecycle dispatch layer to keep runtime execution, telemetry, and public hooks separated.
- Added `Graph.validate()` and typed graph exceptions for validation, serialization, compilation, and rendering failures.
- Added `Graph.compile()` plus public compiled graph snapshot types for normalized graph inspection and shared graph internals.
- Added explicit runtime and structural identity fields across compiled graphs, serialized graph payloads, hook events, and OpenTelemetry span attributes.
- Added regression coverage for:
  - workflow and subflow execution isolation
  - run-concurrent fail-fast cancellation behavior
  - cancellation telemetry
  - detached state snapshots
  - store atomicity
  - plural-sink workflow and subflow execution semantics
  - graph serialization consistency for nested subflows
  - lifecycle hook ordering and failure isolation

### Changed

- `BaseStore.get_state()` now returns a detached deep snapshot.
- `BaseStore.set_state()` now validates and commits atomically against the current locked state.
- Parent workflow loop protection and execution counts now stay scoped to the current workflow rather than absorbing child subflow internals.
- `RunConcurrent` no longer behaves like raw `asyncio.gather()`; sibling failures now cancel pending siblings deterministically.
- Graph traversal now follows the first matching edge in declared order.
- Workflows and subflows now terminate when any declared sink is reached, and dead ends on non-sink nodes raise.
- Workflows and subflows now validate freshly created graphs before execution by default, with an opt-out `validate_graph=False` runtime parameter for targeted testing and debugging.
- Graph validation, traversal adjacency, and serialization now all run through one compiled graph snapshot per graph instance.
- Graph serialization now preserves multiple same-tail/head subflow edges and records explicit runtime and structural identity fields such as `graphStructuralId`, `nodeRuntimeId`, `nodeStructuralId`, and `edgeStructuralId`.
- `Graph` definitions now freeze their source, sinks, and edges at construction time so compiled graph snapshots cannot silently go stale after graph-shape mutation.
- DOT/Graphviz rendering now consumes `CompiledGraph` directly instead of routing through serialized JSON, and identical graph shapes now produce stable DOT output across fresh graph builds.
- Mermaid rendering now consumes `CompiledGraph` directly, renders concurrent groups and subflow detail sections from the compiled graph snapshot, and produces stable structural output across fresh graph builds with the same topology.
- OpenTelemetry span attributes now use explicit identity names such as `junjo.executable_runtime_id`, `junjo.executable_structural_id`, and `junjo.enclosing_graph_structural_id` instead of the old generic `junjo.id` and `junjo.parent_id` keys.
- OpenTelemetry and hook payloads now use `executable_definition_id` and `parent_executable_definition_id` instead of the older generic `definition_id` naming on those surfaces.
- Workflow telemetry now records `junjo.workflow.execution_graph_snapshot` to make it explicit that the graph payload is an execution-scoped compiled snapshot containing both runtime and structural identities.
- `on_state_changed` hook payloads and state-change telemetry context now identify the active executable that performed the mutation, rather than mixing workflow metadata with node or subflow runtime identities.
- Lifecycle observation examples and docs now show hook registration as a separate concern from workflow definition.
- Public docstrings and examples were updated to reflect the current execution, hooks, and result APIs.

### Removed

- Removed `src/junjo/telemetry/hook_manager.py`.
- Removed `src/junjo/telemetry/hook_schema.py`.

## 0.62.1 - 2026-02-14

This patch release focuses on updates to the AI Chat example.

### Changed

- Restored direct Gemini node usage across `examples/ai_chat` workflows instead of routing through provider abstractions.
- Standardized Gemini model usage to `gemini-3-flash-preview` for text/schema generation and `gemini-2.5-flash-image` for image generation/editing flows.
- Hardened Gemini schema request handling for empty/blocked responses and max-token edge cases.
- Updated `examples/ai_chat/README.md` and backend `.env.example` so Gemini is the default path with Grok as an optional experimentation path.

## 0.62.0 - 2026-02-08

This release is primarily a cleanup and polish pass across existing features.
It also includes a versioning decision: Junjo stays on its own line at `0.62.0`
and intentionally diverges from Junjo AI Studio version numbering.

### Highlights

- Modernized examples and docs, especially around telemetry and AI Studio naming.
- Upgraded `examples/ai_chat` from Gemini-centered flows to xAI Grok integration.
- Simplified and standardized developer tooling (Python pinning, Ruff upgrades, lockfile refresh).
- Refactored Graphviz generation internals in `Graph` for maintainability while preserving output behavior.

### Changed

- Updated package metadata and docs terminology from "Junjo Server" to "Junjo AI Studio".
- Added and expanded docs for deployment, Docker, OpenTelemetry usage, and getting started flows.
- Updated root and example Ruff versions to `0.15.0`.
- Updated examples to use current factory-driven workflow patterns more consistently.
- Improved prompt wording and realism in AI chat example flows.

### Removed

- Removed deprecated pre-OpenTelemetry architecture artifacts and legacy telemetry proto/client code under `src/junjo/telemetry/junjo_server/`.
- Removed `src/junjo/telemetry/junjo_server_otel_exporter.py` in favor of the renamed exporter module.
- Removed `src/junjo/app.py`.
- Removed `src/junjo/react_flow/schemas.py`.

### Added

- Added `src/junjo/telemetry/junjo_otel_exporter.py` (`JunjoOtelExporter`) as the current telemetry exporter entrypoint.
- Added docs UI branding assets (favicon and sidebar branding template updates).

### Compatibility Notes

- This is mostly non-feature cleanup/polish, but consumers importing removed internal modules will need to migrate imports.
- Example projects changed substantially; treat `examples/ai_chat` as an updated reference implementation rather than a drop-in patch.
