# Junjo Agent chat frontend

This is the intentionally small browser client for the `ai_chat` Horizon 2
example. It demonstrates one synchronous application turn while keeping
execution and telemetry ownership in the Python backend.

The frontend has three API reads/writes:

- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/turns` with `{ "text": "..." }`

Every response is validated at the API boundary with a strict Zod schema. The
turn response contains the committed user message, committed assistant message,
Workflow run ID, and Agent run ID. The client upserts those returned messages
directly in server response order and performs no polling or follow-up fetch.
Turn text is limited to 2,500 characters. A message image must include nonempty
`image_alt` text, and conversation selection remains fixed while a turn runs so
that the response cannot be applied to a different conversation.

An admitted Agent execution failure is a server error with one strict envelope:
`detail`, `agent_run_id`, and `termination_reason`. The client keeps that identity
visible so a failed browser turn can be found directly in Studio. Relative image
paths are resolved against the same API origin used for JSON requests.

## Run

Use Node.js 22 or newer. Start the example backend on port `8000`, then:

```bash
npm ci
npm run dev
```

Vite proxies `/api` to `http://localhost:8000` in development. Set
`VITE_API_BASE_URL` only when the API is hosted at a different origin. Its value
must be an absolute HTTP origin such as `https://chat-api.example.com`; paths,
query strings, embedded credentials, and fragments are rejected.

## Validate

```bash
npm test
npm run lint
npm run build
```

The tests lock the JSON contracts and prove that a synchronous turn directly
upserts the two returned messages, records evidence IDs, preserves existing
messages on failure, and never issues a follow-up message request.
