# Junjo Example - Base

This is meant to be the most basic example of Junjo's implementation. 

It shows junjo being instantiated, a simple graph with a condition, and telemetry that logs to Junjo Server.

### Run the example

```bash
# Run from the root directory of junjo
$ python -m examples.base.main
$ uv run -m examples.base.main
```

The graph should run, logging node executions and state changes.

If Junjo Server is running, it will receive telemetry.