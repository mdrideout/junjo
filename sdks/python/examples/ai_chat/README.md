# Junjo AI Chat: Hybrid Workflow and Agent Example

This application is the Horizon 2 proof for composing Junjo's deterministic
Workflows with its bounded Agent runtime while preserving the original AI Chat
product. It deliberately keeps
application persistence, HTTP transport, and image rendering outside Junjo.

The canonical turn is:

```text
ChatApplication admits a server-owned, versioned Turn
  -> Handle Message Workflow
       -> Load Turn Context (concurrent)
            -> LoadRecentContextNode
            -> LoadContactNode
       -> AssessMessageDirectiveNode
       -> one branch
            -> CreateWorkResponseNode
            -> CreateDateIdeaResponseNode
            -> Create Image Response Subflow
            -> CreateGeneralAgentResponseNode
                 -> AI Chat Agent
                      -> optional history/contact Tool
                      -> optional image Tool
                           -> Create Chat Image Workflow
       -> PersistOutcomeNode
  -> ChatApplication reconciles the terminal Workflow reference
```

This proves both truthful composition directions without an `AgentNode`, a
`WorkflowTool`, a generated Graph, or a shared Store:

- `Workflow -> Node -> Agent`
- `Agent -> Tool -> Workflow -> Nodes`

## Architecture

The backend uses small explicit layers:

- `domain`: immutable versioned Turn values and narrow persistence/capability
  protocols; no FastAPI, SQLite, or Junjo orchestration.
- `application`: the reusable Agent, typed Tools, image Workflow, turn
  Workflow, and application-owned mappings between them.
- `adapters`: in-memory and SQLite persistence, deterministic SVG rendering,
  and the stateless demo ModelDriver.
- `api`: strict admission, polling, contact, and read transport. A successful
  Turn POST returns the persisted admitted Turn; background execution updates
  the same object until it is terminal.

SQLite stores canonical Turn JSON plus identity and conversation-order
projections. Messages, recent context, and history search are derived from
Turn objects. The browser reloads those objects; it does not keep a separate
ephemeral map of execution evidence.

Provider selection is explicit. `AI_CHAT_MODEL_PROVIDER=demo` uses the
deterministic concurrent-safe ModelDriver and SVG renderer. `gemini` and `grok`
select real text and image adapters and require `GEMINI_API_KEY` or
`XAI_API_KEY`; neither selection falls back to the demo provider. The canonical
tests inject Junjo's `ScriptedModelDriver` and never require a secret.

## Run

Compose is the canonical full-stack run path. From
`sdks/python/examples/ai_chat`:

```bash
docker compose up --build
```

Open `http://localhost:26251`. The browser calls the exposed FastAPI service at
`http://localhost:26252` directly. Compose and native execution intentionally
use these same origins; the example has no reverse proxy or container-only
browser networking model.

Compose runs the Vite development server and FastAPI together in pinned Node
22 and Python 3.13 images. The SDK and backend source directories are mounted
into the backend container, and the frontend source is mounted into the Vite
container. FastAPI/watchfiles reloads after Python changes and Vite HMR updates
the browser after frontend changes. Polling is enabled explicitly so both paths
work consistently through Docker Desktop bind mounts. Dependency-file changes
still require `docker compose up --build`.

SQLite and generated images live in the named `ai-chat-data` volume; frontend
dependencies live in `ai-chat-frontend-node-modules`. Stop the stack without removing its data with
`docker compose down`. To reset the example completely, explicitly remove the
volume:

```bash
docker compose down --volumes
```

The checked-in defaults and the local `.env` use Junjo-specific ports that are
unlikely to collide with other development services:

```bash
AI_CHAT_FRONTEND_PORT=26251
AI_CHAT_BACKEND_PORT=26252
```

Compose uses each configured port both inside the container and on the host, so
the FastAPI and Vite startup messages show the same URLs used by the browser.
Edit `.env` only if these ports ever need to change.

### Native component development

Native processes expose the same origins as Compose. From `sdks/python`:

```bash
uv sync --python 3.13 --package junjo-ai-chat-example --group dev
uv run --package junjo-ai-chat-example fastapi dev \
  --port 26252 \
  examples/ai_chat/backend/src/ai_chat/main.py
```

In another terminal, from `sdks/python/examples/ai_chat/frontend`:

```bash
npm ci
npm run dev
```

The native backend seeds one `demo` conversation in
`backend/runtime-data/chat.sqlite3`. Delete `backend/runtime-data` to reset only
native application data.

## API contract

- `GET /api/conversations`
- `GET /api/config`
- `GET /api/conversations/{conversation_id}/turns`
- `GET /api/turns/{turn_id}`
- `POST /api/contacts` with `{ "sex": "male" | "female" }`
- `POST /api/conversations/{conversation_id}/turns` with `{"text": "..."}`

A message exposes `image_url` and `image_alt` as a strict pair: both are null,
or both are present with nonempty accessible alt text.

FastAPI owns request validation and returns 422 before admission. The server
allocates Turn identity and sequence, persists input before execution, and
allows only one active Turn per conversation. The POST returns HTTP 202 with
that admitted object. The client resolves terminal success or failure with
`GET /api/turns/{turn_id}`; failed and cancelled Turns therefore survive reload.

## Deterministic validation

From `sdks/python`:

```bash
uv run --package junjo-ai-chat-example ruff check examples/ai_chat/backend
uv run --package junjo-ai-chat-example ty check --error-on-warning \
  examples/ai_chat/backend/src
uv run --package junjo-ai-chat-example pytest -q examples/ai_chat/backend/tests
```

The backend suite retains the nine original Horizon 2 Agent scenarios and adds
the restored product boundaries: concurrent context loading, deterministic
work/date/image branches, general Workflow-to-Agent handling, contact creation
with avatar Subflow, asynchronous Turn admission and polling, versioned
persistence, explicit provider selection, and the complete hybrid telemetry
hierarchy with independent Store replay.

## Optional Junjo AI Studio telemetry

Telemetry is intentionally optional. No telemetry or provider work occurs at
module import. When `JUNJO_AI_STUDIO_API_KEY` is configured, the FastAPI
lifespan creates the exporter after process startup and flushes it only after
application cleanup completes. The lifespan owns both the OpenTelemetry
`TracerProvider` and `MeterProvider`, attempts every flush and shutdown path,
and leaves neither exporter worker thread alive. Both providers are installed
as the process-wide OpenTelemetry owners, and startup fails explicitly if
another provider already owns the process.

The Studio stack remains independent from this application stack. Copy the
single example environment file only when telemetry or debug links are needed:

```bash
# From sdks/python
cp examples/ai_chat/.env.example examples/ai_chat/.env
```

Compose loads that file automatically. It routes OTLP to
`host.docker.internal:26155`, including on Linux through an explicit
`host-gateway` mapping. For a native backend, explicitly load the same file
from `sdks/python`:

```bash
uv run --env-file examples/ai_chat/.env \
  --package junjo-ai-chat-example fastapi dev \
  examples/ai_chat/backend/src/ai_chat/main.py
```

The default local Studio endpoints are:

- UI: `http://localhost:26153`
- API: `http://localhost:26154`
- OTLP gRPC ingestion: `localhost:26155`

Studio shows the Agent as a dynamic operation timeline and each nested
Workflow with its normal Graph and independently reconstructed Store.

Set `AI_CHAT_DEBUG=true` and `AI_CHAT_STUDIO_UI_URL=http://localhost:26153` to
show per-Turn Studio links. The links use Studio's authenticated execution
resolver, which translates the persisted Workflow or Agent runtime ID into its
trace and span after bounded polling for ingestion delay. Debug mode changes
presentation only; execution references and correlation are always recorded.

The release-only distribution smoke runs the complete path against the exact
Studio images: FastAPI and SQLite, OTLP ingestion, semantic Agent and Workflow
Store APIs, and a signed-in browser inspection of the Agent Tool timeline and
nested Workflow. The credential-free evidence JSON and Studio screenshot are
retained as CI artifacts; smoke credentials are environment-only.
