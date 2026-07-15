# Junjo AI Chat backend

This package is the backend half of Junjo's restored hybrid Workflow and Agent
example. The canonical architecture, run instructions, API contract,
telemetry configuration, and acceptance scenarios live in the
[example README](../README.md).

The package intentionally contains only application-owned domain,
orchestration, provider/persistence adapter, eval, and HTTP layers. Junjo owns
Agent and Workflow execution; the application owns prompts, providers,
persistence, transport, image artifacts, and product-quality evaluation.

The canonical full-stack development environment is the two-service
`compose.yaml` in the parent directory. This backend image is built from the
`sdks/python` workspace context so it installs the exact local Junjo source and
the AI Chat package from the same lockfile. Compose mounts its named data
volume at `/data`; native execution uses `runtime-data` beside this package.
The parent `.env` is the only Compose environment file and is required; do not
create a second backend environment file.
The SDK and backend source trees are bind-mounted, and watchfiles polling is
enabled, so Python edits reload the running FastAPI process without rebuilding
the image. Dependency changes still require a rebuild.
Both execution modes expose the backend on `http://localhost:26252` by default.
