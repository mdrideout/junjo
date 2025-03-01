# Junjo Example - AI Chat

This is a more complete example of Junjo, showcasing:

- An AI Chat application that can make decisions to execute specific workflows
- A test-drive-development approach to AI development
- Enahnced telemetry with LLM information

#### Stack

- Vite + React Frontend
- FastAPI Backend

## Run the example

```bash
# FRONTEND (from ./frontend)
# Ensure all packages are installed
$ npm i

# Start the frontend 
$ npm run dev


# BACKEND (from ./backend)
# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e .

# Start the backend
$ fastapi dev main.py
```