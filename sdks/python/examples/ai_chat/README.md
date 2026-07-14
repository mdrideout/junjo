# Junjo AI Chat: Workflow, Agent, Telemetry, and Eval Application

AI Chat is Junjo's realistic AI-application proving ground. It uses live models
inside explicit Workflow Nodes for known procedures and a bounded Agent for the
open-ended response path. It is not a credential-free Agent test harness.

The application owns its domain objects, persistence, prompts, providers,
transport, UI, and evals. Junjo owns faithful Workflow, Node, Subflow, Agent,
Tool, Store, correlation, and telemetry execution.

## Product topology

Contact creation:

```text
Create Contact Workflow
  -> concurrently select age, personality traits, and US coordinates/location
  -> generate a complete biography with the selected live language model
  -> generate a coherent name with the selected live language model
  -> Avatar Subflow
       -> generate a photography concept
       -> generate a realistic profile image
  -> persist versioned Contact and Conversation JSON objects
```

One conversation Turn:

```text
ChatApplication admits a server-owned, versioned Turn
  -> Chat Turn Workflow
       -> concurrently load the Contact and bounded recent history
       -> classify the response directive with the live language model
       -> work: persona/history-conditioned model response
       -> date: specific persona/location-conditioned model response
       -> image: shared Image Workflow
            -> generate photo inspiration
            -> edit from the Contact avatar for visual continuity
            -> generate/retain accompanying text
       -> general: persona-aware Junjo Agent
            -> optional older-history search Tool
            -> optional image Tool -> the same shared Image Workflow
       -> persist the selected response and Agent identity
  -> reconcile the terminal Workflow identity on the Turn
```

This proves both composition directions without an `AgentNode`, generated
Graph, shared Store, or duplicate image procedure:

- `Workflow -> Node -> Agent`
- `Agent -> Tool -> Workflow -> Nodes`

Mandatory context is loaded by the Workflow on every Turn. The Agent receives
the complete Contact and bounded recent history; it does not need a redundant
Contact Tool. Optional older-history search and image creation remain Tools.

## Architecture

- `domain`: immutable, versioned application values and narrow capability
  protocols. It does not import FastAPI, SQLite, provider SDKs, or Junjo.
- `application`: explicit Workflow/Graph/Node/Subflow definitions, Agent and
  Tools, prompts, application services, and application-owned live evals.
- `adapters`: SQLite/versioned-JSON persistence and explicit Gemini or Grok
  language, image, and Agent-driver adapters.
- `api`: strict HTTP projections, durable Turn admission, polling, and safe
  debug configuration.
- `frontend`: the original multi-contact chat experience plus an optional
  per-Turn Studio diagnostics layer.

`LanguageModel` and `ImageModel` are application ports for bounded Node work.
Junjo's `ModelDriver` is a separate boundary for translating the Agent
operation loop. Provider selection is explicit and missing credentials fail
startup; there is no demo provider, SVG substitute, or fallback chain.

SQLite stores canonical versioned Contact, Conversation, and Turn JSON with
only identity/order relationship projections. The browser reloads durable
Turns and runtime references rather than maintaining a second evidence model.

## Run the full stack

Create the ignored local environment file and configure one live provider:

```bash
cp .env.example .env
```

For Gemini (the default):

```dotenv
AI_CHAT_MODEL_PROVIDER=gemini
GEMINI_API_KEY=...
```

For Grok:

```dotenv
AI_CHAT_MODEL_PROVIDER=grok
XAI_API_KEY=...
```

Then, from `sdks/python/examples/ai_chat`:

```bash
docker compose up --build
```

Open `http://localhost:26251`; FastAPI is exposed directly at
`http://localhost:26252`. Compose uses the same origins as native development
and intentionally has no reverse proxy.

The backend and frontend use bind mounts plus watchfiles/Chokidar polling, so
Python changes restart FastAPI and frontend changes use Vite HMR. Dependency
changes require `docker compose up --build` again. SQLite and generated images
live in `ai-chat-data`; reset them explicitly with:

```bash
docker compose down --volumes
```

The new versioned document schema uses `chat-v3.sqlite3`. There are no database
migrations or seeded contacts; create the first contact in the UI.

### Native development

From `sdks/python`:

```bash
uv sync --python 3.13 --package junjo-ai-chat-example --group dev
uv run --env-file examples/ai_chat/.env --package junjo-ai-chat-example \
  fastapi dev --port 26252 examples/ai_chat/backend/src/ai_chat/main.py
```

From `sdks/python/examples/ai_chat/frontend` in another terminal:

```bash
npm ci
npm run dev
```

## Junjo AI Studio

Configure the Studio exporter independently:

```dotenv
JUNJO_AI_STUDIO_API_KEY=...
JUNJO_AI_STUDIO_HOST=host.docker.internal
JUNJO_AI_STUDIO_PORT=26155
JUNJO_AI_STUDIO_INSECURE=true
```

The application emits FastAPI, provider, Workflow, Node, Subflow, Agent, Tool,
and Store evidence with one trusted application correlation per Contact or
Turn. Studio displays Agent operations and nested Tools alongside the normal
Workflow Graph and reconstructed Store histories.

Enable the optional browser diagnostics layer with:

```dotenv
AI_CHAT_DEBUG=true
AI_CHAT_STUDIO_UI_URL=http://localhost:26153
```

The browser receives only the Studio UI origin and persisted runtime IDs. It
never receives the Studio API key. Deep links use Studio's authenticated
runtime-identity resolver and tolerate normal ingestion delay.

## Eval-driven development

Ordinary tests protect deterministic application mechanics only: versioned
persistence, server-owned Turn lifecycle, HTTP/schema boundaries, configuration
safety, frontend interactions, and telemetry lifetime. Junjo's SDK suite owns
the Agent/Tool/runtime matrices.

Live evals own product quality. Biography and directive datasets are colocated
with their application capabilities and execute real Nodes through
`junjo.evaluate_node()`, preserving normal Node/Store telemetry and exact run
identity. Run them deliberately with the same provider environment:

```bash
uv run --env-file examples/ai_chat/.env --package junjo-ai-chat-example \
  pytest -m live_eval \
  examples/ai_chat/backend/src/ai_chat/application/contact_workflow/evals \
  examples/ai_chat/backend/src/ai_chat/application/turn_workflow/evals -v -s
```

When the Studio variables are present, each eval run is exported and correlated
as `ai_chat.eval_case`; failures include the exact run ID. The application owns
its cases, rubrics, judges, and thresholds. A scripted model is never treated as
proof of AI product behavior.

## Conventional validation

From `sdks/python`:

```bash
uv run ruff check examples/ai_chat/backend
uv run ty check --error-on-warning examples/ai_chat/backend/src
uv run pytest -q examples/ai_chat/backend/tests
```

From `sdks/python/examples/ai_chat/frontend`:

```bash
npm test -- --run
npm run lint
npm run build
```

## HTTP contract

- `GET /api/config`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}/turns`
- `GET /api/turns/{turn_id}`
- `POST /api/contacts` with `{ "sex": "male" | "female" }`
- `POST /api/conversations/{conversation_id}/turns` with `{ "text": "..." }`

The server allocates Turn identity and sequence, persists input before model
execution, and permits only one active Turn per conversation. POST returns 202
with the admitted Turn; terminal success or failure is resolved by server ID and
survives reload. Image URL and accessible alt text are an inseparable pair.
