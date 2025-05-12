# Junjo Example - Base

This is a basic single-file implementation of Junjo's Graph Workflow Execution. It includes:

- A single workflow
- The Graph
- A few top level nodes
- Concurrent execution
- A Subflow
- A Conditional that determines the next node based on the results of a state update
- An opentelemetry exporter for Junjo Server (optional / not required)

See the **ai_chat** example for a more advanced frontend / backend E2E experience that utilizes LLM API calls.

### Run the example

> Note: the following commands assume your terminal is located in this directory.

- The graph workflow will run, logging node executions and state changes.
- If [Junjo Server](https://github.com/mdrideout/junjo-server) is running, it will receive telemetry.
  - Requires you to generate an API key inside the Junjo Server interface, and add it as a `.env` variable here.

```bash
# Run commands from this directory
#   - (Using uv package manager https://docs.astral.sh/uv/)
#
# Create a virtual environment if one doesn't exist yet (tested down to python 3.11)
$ uv venv --python 3.11

# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e ".[dev]"

# Run from this directory
$ python -m src.base.main
$ uv run -m src.base.main
```