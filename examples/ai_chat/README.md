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
- Image generation / image edit: `gemini-2.5-flash-image`

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
# Ensure all packages are installed (Python 3.11)
$ uv sync --python 3.11 --package app

# Start the backend
$ uv run --package app fastapi dev src/app/main.py

# Visualize the graph
$ uv run --package app -m app.visualize
```

Environment variables live in `backend/.env.example` (copy to `backend/.env` and fill in the keys you want to use).


### Telemetry

Have the [junjo-ai-studio](https://github.com/mdrideout/junjo-ai-studio) running on your machine to see the telemetry and graph visualizations.

### Clearing the SQLite database

The SQLite database (see `backend/src/app/db/db_config.py`) should persist inside the `backend/sqlite-data` folder in this project.

**Delete `backend/sqlite-data`** to clear the sqlite database and start fresh. A new database will be created automatically at the next app startup.
