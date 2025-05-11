# Junjo Example - Base

This is meant to be the most basic example of Junjo's implementation. 

It shows junjo being instantiated, a simple graph with a condition, and telemetry that logs to Junjo Server.

### Development

It is recommend you develop this example from this directory, with the activated venv, and not the junjo root.

### Run the example (from this directory)

- **This example has been configured to work nested in the junjo project `examples/base` directory.**
- The graph will run, logging node executions and state changes.
- If Junjo Server is running, it will receive telemetry.

```bash
# From The Junjo Library Root Directory
#   - (Using uv package manager https://docs.astral.sh/uv/)
#
# Create a virtual environment if one doesn't exist yet (recommend python 3.12)
$ uv venv --python 3.11

# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e .

# Run from this directory
$ python -m src.base.main
$ uv run -m src.base.main
```