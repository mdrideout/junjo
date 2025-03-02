# Junjo Example - AI Chat

This is a more complete example of Junjo, showcasing:

- An AI Chat application that can make decisions to execute specific workflows
- A test-drive-development approach to AI development
- Enahnced telemetry with LLM information

#### Stack

- Vite + React Frontend
- FastAPI Backend
- SQLite for persistence

## Run the example

```bash
# FRONTEND (from ./frontend)
# Ensure all packages are installed
$ npm i

# Start the frontend 
$ npm run dev

# -------------------------#

# BACKEND (from ./backend) 
#   - Using uv package manager https://docs.astral.sh/uv/)
#
# Create a virtual environment if one doesn't exist yet (recommend python 3.12)
$ uv venv --python 3.12

# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e .

# Start the backend
$ fastapi dev src/app/main.py
```

### Clearing the SQLite database

The SQLite database (see `.backend/src/app/db/db_config.py`) should persist inside the `.backend/sqlite-data` folder in this project.

**Delete `.backend/sqlite-data`** to clear the sqlite database and start fresh. A new database will be created automatically at the next app startup.