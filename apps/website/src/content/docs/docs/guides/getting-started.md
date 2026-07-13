---
title: Getting started
description: Build and execute your first Junjo workflow using the maintained Python SDK guide.
---

Junjo applications define domain work as nodes, connect those nodes with a
graph, and execute that graph through a `Workflow`. Each execution creates an
isolated graph and store, so reusable workflow definitions do not become live
mutable run containers.

## Install the Python SDK

Junjo requires Python 3.11 or newer:

```bash
pip install junjo
```

## Follow the maintained tutorial

The Python SDK owns the complete, runnable tutorial and API documentation:

1. Work through the [getting started tutorial](https://python-api.junjo.ai/getting_started.html).
2. Compare it with the [runnable source](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/getting_started).
3. Construct a `Workflow` with a graph factory and store factory.
4. Execute it asynchronously with `result = await workflow.execute()`.
5. Read the detached final state from `result.state`.

The graph describes valid execution paths. The store owns validated state
transitions. The workflow coordinates an isolated execution and returns its
result. Keeping these responsibilities separate makes application behavior
straightforward to test and inspect.

## Add observability when needed

Junjo instruments workflow execution with OpenTelemetry. Configure an exporter
at the application boundary to send traces to your existing observability
platform or to Junjo AI Studio. Telemetry is a first-class runtime concern; it
does not depend on optional public hooks.

See the [OpenTelemetry guide](https://python-api.junjo.ai/opentelemetry.html) and
[Junjo AI Studio guide](https://python-api.junjo.ai/junjo_ai_studio.html) for
current configuration examples.
