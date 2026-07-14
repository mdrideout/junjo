# Junjo Agent chat frontend

This is the intentionally small browser client for the `ai_chat` Horizon 2
example. It demonstrates server-admitted background Turns while keeping
execution and telemetry ownership in the Python backend.

The frontend has six API reads/writes:

- `GET /api/config`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}/turns`
- `GET /api/turns/{turn_id}`
- `POST /api/contacts`
- `POST /api/conversations/{conversation_id}/turns` with `{ "text": "..." }`

Every response is validated at the API boundary with a strict Zod schema. The
Turn response is the persisted, schema-versioned application aggregate. It
contains lifecycle status, messages, context-policy identity, failure evidence,
and Workflow/Agent run references. The POST returns the durable admitted Turn;
the browser shows it immediately, then polls only that server-owned identity
until it reaches a terminal state.
Turn text is limited to 2,500 characters. A message image must include nonempty
`image_alt` text, and conversation selection remains fixed while a turn runs so
that the response cannot be applied to a different conversation.

An admitted execution failure is a typed problem containing the terminal Turn.
The client keeps that durable failure and its known runtime identities visible
after reload. When the backend enables debug presentation, the diagnostics
panel links those identities through Studio's authenticated resolver; no Studio
credential is exposed to this application. Relative image paths are resolved
against the same API origin used for JSON requests.

## Run

The canonical full stack starts from the parent directory with
`docker compose up --build`. It exposes this Vite server at
`http://localhost:26251` and FastAPI at `http://localhost:26252`. The frontend
directory is bind-mounted and Chokidar polling is enabled, so Vite HMR applies
source changes through Docker Desktop. Dependency changes require a rebuild.

For native component development, use Node.js 22 or newer, start the backend
on port `26252`, then:

```bash
npm ci
npm run dev
```

The browser calls `http://localhost:26252` directly by default; Vite does not
proxy API traffic. Set `VITE_API_BASE_URL` only when the exposed API origin is
different. Its value must be an absolute HTTP origin such as
`https://chat-api.example.com`; paths, query strings, embedded credentials,
and fragments are rejected.

## Validate

```bash
npm test
npm run lint
npm run build
```

The tests lock the JSON contracts and prove that admitted, completed, and
failed Turns retain execution references, contact creation and the restored UI
remain available, and debug-only controls construct exact Studio resolver
links.
