# Junjo AI Chat: Hybrid Workflow and Agent Example

This credential-free application is the Horizon 2 proof for composing Junjo's
deterministic Workflows with its bounded Agent runtime. It deliberately keeps
application persistence, HTTP transport, and image rendering outside Junjo.

The canonical turn is:

```text
Chat Turn Workflow
  -> PersistInputNode
  -> ExecuteAgentNode
       -> AI Chat Agent
            -> optional read-only history/contact Tool
            -> optional image Tool
                 -> Create Chat Image Workflow
                      -> PrepareImagePromptNode
                      -> RenderImageNode
  -> PersistResultNode
```

This proves both truthful composition directions without an `AgentNode`, a
`WorkflowTool`, a generated Graph, or a shared Store:

- `Workflow -> Node -> Agent`
- `Agent -> Tool -> Workflow -> Nodes`

## Architecture

The backend uses small explicit layers:

- `domain`: immutable application values and narrow persistence/capability
  protocols; no FastAPI, SQLite, or Junjo orchestration.
- `application`: the reusable Agent, typed Tools, image Workflow, turn
  Workflow, and application-owned mappings between them.
- `adapters`: in-memory and SQLite persistence, deterministic SVG rendering,
  and the stateless demo ModelDriver.
- `api`: strict synchronous request/response transport. A successful POST
  directly returns the two persisted messages and execution identities.

The default ModelDriver is deterministic and concurrent-safe. It needs no
provider SDK, network call, credential, sleep, background task, or polling
loop. The canonical tests inject Junjo's `ScriptedModelDriver`.

## Run

From `sdks/python`:

```bash
uv sync --python 3.13 --package junjo-ai-chat-example --group dev
uv run --package junjo-ai-chat-example fastapi dev \
  examples/ai_chat/backend/src/ai_chat/main.py
```

In another terminal, from `sdks/python/examples/ai_chat/frontend`:

```bash
npm ci
npm run dev
```

The backend seeds one `demo` conversation in
`backend/runtime-data/chat.sqlite3`. Delete `backend/runtime-data` to reset the
local application data.

## API contract

- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/turns` with `{"text": "..."}`

A message exposes `image_url` and `image_alt` as a strict pair: both are null,
or both are present with nonempty accessible alt text.

FastAPI owns request validation and returns 422 before execution. Once a turn
reaches the application, every typed `AgentError` is a server-side execution
failure and returns HTTP 500 with exactly `detail`, `agent_run_id`, and
`termination_reason`. This keeps failed execution identity queryable instead
of misrepresenting admitted failures as malformed HTTP input.

## Deterministic validation

From `sdks/python`:

```bash
uv run --package junjo-ai-chat-example ruff check examples/ai_chat/backend
uv run --package junjo-ai-chat-example ty check --error-on-warning \
  examples/ai_chat/backend/src
uv run --package junjo-ai-chat-example pytest -q examples/ai_chat/backend/tests
```

The backend suite names and proves all nine Horizon 2 scenarios: direct
completion, history Tool selection, nested image Workflow selection, malformed
arguments, nested failure propagation, loop limits, cancellation, concurrent
isolation, and the complete in-memory telemetry hierarchy with independent
Store replay.

## Optional Junjo AI Studio telemetry

Telemetry is intentionally optional. No telemetry or provider work occurs at
module import. When `JUNJO_AI_STUDIO_API_KEY` is configured, the FastAPI
lifespan creates the exporter after process startup and flushes it only after
application cleanup completes. The lifespan owns both the OpenTelemetry
`TracerProvider` and `MeterProvider`, attempts every flush and shutdown path,
and leaves neither exporter worker thread alive. Both providers are installed
as the process-wide OpenTelemetry owners, and startup fails explicitly if
another provider already owns the process.

From `sdks/python`, copy and edit the example environment file when exporting
to Studio. Uncomment the values you intend to set, then explicitly load that
file when starting the backend:

```bash
cp examples/ai_chat/backend/.env.example examples/ai_chat/backend/.env
uv run --env-file examples/ai_chat/backend/.env \
  --package junjo-ai-chat-example fastapi dev \
  examples/ai_chat/backend/src/ai_chat/main.py
```

The default local Studio endpoints are:

- UI: `http://localhost:26153`
- API: `http://localhost:26154`
- OTLP gRPC ingestion: `localhost:26155`

Studio shows the Agent as a dynamic operation timeline and each nested
Workflow with its normal Graph and independently reconstructed Store.

The release-only distribution smoke runs the complete path against the exact
Studio images: FastAPI and SQLite, OTLP ingestion, semantic Agent and Workflow
Store APIs, and a signed-in browser inspection of the Agent Tool timeline and
nested Workflow. The credential-free evidence JSON and Studio screenshot are
retained as CI artifacts; smoke credentials are environment-only.
