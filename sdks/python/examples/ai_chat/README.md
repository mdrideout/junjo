# Junjo Example - AI Chat

This is a more complete example of Junjo, showcasing:

- An AI Chat application that can make decisions to execute specific workflows
- A test-drive-development approach to AI development
- Enahnced telemetry with LLM information

#### Stack

- Vite + React Frontend
- FastAPI Backend
- SQLite for persistence

## AI provider

This example is currently wired up to use **Gemini** for all workflow AI calls via `GeminiTool`.

Current node defaults:

- Text generation / structured output: `gemini-3-flash-preview`
- Image generation / image edit: `gemini-3.1-flash-image-preview`

For experimentation, you can switch specific nodes to `GrokTool` (or back) by editing the tool import and model in
the node files under `backend/src/app/workflows/`.

## Run the example

```bash
# FRONTEND (from ./frontend)
# Ensure all packages are installed
$ npm i

# Start the frontend 
$ npm run dev

# -------------------------#

# BACKEND (from ./backend) 
#   - Using uv package manager https://docs.astral.sh/uv/
#
# This repo is a `uv` workspace. The virtual environment lives at the repo root
# (`../../../.venv` from here), not inside this backend directory.
#
# Ensure all packages are installed (Python 3.13)
$ uv sync --python 3.13 --package app

# Start the backend
$ uv run --package app fastapi dev src/app/main.py

# Visualize the graph
$ uv run --package app -m app.visualize
```

Environment variables live in `backend/.env.example` (copy to `backend/.env`). Which keys you need:

- `JUNJO_AI_STUDIO_API_KEY` — **required** for the backend to start (telemetry initialization raises on import without it). Generate one inside the Junjo AI Studio interface.
- `GEMINI_API_KEY` — required for the chat workflows; all nodes are currently wired to `GeminiTool`.
- `XAI_API_KEY` — optional; only needed if you switch nodes to `GrokTool`.


### Telemetry

Have the [junjo-ai-studio](https://github.com/mdrideout/junjo/tree/master/apps/studio) running on your machine to see the telemetry and graph visualizations.

AI Chat runs directly on your local machine with `uv run`. It sends Junjo telemetry to the local Junjo AI Studio ingestion endpoint on `localhost:26155`.

For a local Docker Compose AI Studio stack, the default local ports are:

- UI: `http://localhost:26153`
- API: `localhost:26154`
- OTLP gRPC ingestion: `localhost:26155`

### Clearing the SQLite database

The SQLite database (see `backend/src/app/db/db_config.py`) should persist inside the `backend/sqlite-data` folder in this project.

**Delete `backend/sqlite-data`** to clear the sqlite database and start fresh. A new database will be created automatically at the next app startup.
