# Junjo AI Studio Frontend

React + TypeScript frontend for the Junjo AI Studio web UI.

## Architecture and conventions

The frontend's state-placement, Redux Toolkit listener middleware, and vertical
slice decisions are owned by
[ADR-002](../docs/adr/002-redux-toolkit-listener-middleware-pattern.md). Shared
interaction primitives are governed by
[ADR-005](../docs/adr/005-studio-frontend-interaction-foundation.md).

Coding agents should use the
[`studio-frontend-react`](../../../.agents/skills/studio-frontend-react/SKILL.md)
skill as the task workflow and read the ADRs for architectural decisions. The
README does not duplicate those rules.

## Running

Primary workflow is the full hot-reload stack from the Studio root (`apps/studio`):

```bash
docker compose up --build
```

From another terminal:

```bash
docker compose logs -f frontend
```

Local URLs are selected by `JUNJO_BUILD_TARGET`:
- `JUNJO_BUILD_TARGET=development` with `COMPOSE_PROFILES=development`: the Vite development server serves the UI on `http://localhost:26151` and proxies API requests to the backend on `http://localhost:26154`
- `JUNJO_BUILD_TARGET=production`: the backend serves the built UI and the API on `http://localhost:26154`, and the `frontend` service does not run

For frontend-only testing/debugging outside Docker:

```bash
cd frontend
npm install
npm run dev
```

Vite serves on `http://localhost:26151` by default. This path is intended for frontend-focused testing/debugging and assumes the backend is reachable at `http://localhost:26154`; set `JUNJO_DEV_BACKEND_URL` to proxy to a backend somewhere else. The supported full-stack workflow is `docker compose up --build` from the Studio root.

## Commands

```bash
cd frontend
npm run test:run
npm run lint
npm run build
```

The production release smoke also runs `npm run test:e2e:agent-live` against
the exact Studio images. It signs in with an ephemeral smoke identity, opens a
live public-SDK Agent execution, verifies its operation and nested Workflow Store
diagnostics, and retains a full-page screenshot. Credentials are accepted only
through `JUNJO_STUDIO_E2E_EXISTING_EMAIL` and
`JUNJO_STUDIO_E2E_EXISTING_PASSWORD`; the evidence JSON contains only runtime
and span identities.

`e2e/live-load.mjs` is not a test. It drives the real pages in several browser
tabs for a fixed time and records what each page showed and how every API
request was answered. The real-world runs in
[`../ingestion/benchmarks/README.md`](../ingestion/benchmarks/README.md)
start it while a load generator sends spans, and take its credentials from
the same two variables.

## Notes

- The app calls the API with same-origin relative URLs under `/api/v1`. In development the Vite server proxies `/api/` and `/health` to the backend, so the browser is same-origin in both modes. The proxy prefix is `/api/` with the trailing slash, because the app has a page at `/api-keys`.
- The frontend is not a released image and has no runtime configuration file. `backend/Dockerfile` builds it, and the backend serves the build.
