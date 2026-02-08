# Changelog

All notable changes to Junjo will be documented in this file.

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

