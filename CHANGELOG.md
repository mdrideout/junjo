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

### Added

- Added `ExecutionResult` as the public completion snapshot for workflows and subflows.
- Added a public `Hooks` API with typed lifecycle events for workflows, subflows, nodes, concurrent execution, and state changes.
- Added an internal lifecycle dispatch layer to keep runtime execution, telemetry, and public hooks separated.
- Added regression coverage for:
  - workflow and subflow execution isolation
  - run-concurrent fail-fast cancellation behavior
  - cancellation telemetry
  - detached state snapshots
  - store atomicity
  - lifecycle hook ordering and failure isolation

### Changed

- `BaseStore.get_state()` now returns a detached deep snapshot.
- `BaseStore.set_state()` now validates and commits atomically against the current locked state.
- Parent workflow loop protection and execution counts now stay scoped to the current workflow rather than absorbing child subflow internals.
- `RunConcurrent` no longer behaves like raw `asyncio.gather()`; sibling failures now cancel pending siblings deterministically.
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
