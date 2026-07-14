# Junjo AI Chat backend

This package is the backend half of Junjo's credential-free hybrid Workflow
and Agent example. The canonical architecture, run instructions, API contract,
telemetry configuration, and acceptance scenarios live in the
[example README](../README.md).

The package intentionally contains only application-owned domain,
orchestration, adapter, and HTTP layers. Junjo owns Agent and Workflow
execution; the application owns persistence, transport, and image rendering.
