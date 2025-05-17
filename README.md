# Junjo 順序

> Japanese Translation: order, sequence, procedure

Junjo helps you build and debug AI workflows with this Graph Workflow Execution library, and our **optional** companion [junjo-server](https://github.com/mdrideout/junjo-server) telemetry server.

<img src="https://raw.githubusercontent.com/mdrideout/junjo/main/junjo-screenshot.png" width="600" />

_junjo-screenshot.png_

### Features

- Organizes your python functions and LLM calls into executable graph workflows
- Produces structured opentelemetry logs compatible with **any opentelemetry destination**
  - Helps you visibly trace AI graph workflow executions
  - Helps you debug where things go wrong
  - Optionally utilize **[junjo-server](https://github.com/mdrideout/junjo-server)** for enhanced telemetry visualiations of the graph

Junjo is a decoupled AI Graph Workflow execution framework for python applications. It is optimized for telemetry, eval-driven-development (test driven prompt engineering), concurrent execution with asyncio, and type safety with Pydantic.

Junjo doesn't change how you build your applications, and will not couple you to this framework. Junjo provides building blocks to wrap and organize your existing python functions into scalable, testable, and improvable workflows.

> 
> There are zero proprietary AI / LLM implementations in Junjo. Use whatever LLM library you want.
> 
> All logs produced are opentelemetry compatible. Exusting otel spans are annotated with workflow execution span wrappers.
> 

It doesn't matter if the functions you add to a Junjo workflow are LLM API calls, database operations, or traditional business logic. You can write your business logic however you want. We just provide a convenient framework for organizing your desired flow into an executable graph.

### Building AI Workflows and Agents as a Graph Workflow

Agentic AI applications use LLMs to determine the order of execution of python functions. These functions may involve LLM requests, API requests, database CRUD operations, etc.

The simplest way to organize functions that can be / need to be executed in a certain order is in the form of a [directed graph](https://en.wikipedia.org/wiki/Directed_graph).

A directed graph gives one the building blocks to create any sort of agentic application, including:

- High precision workflows in the form of a Directed Acyclic Graph (DAG)
- Autonomous AI Agents in the form of dynamically determined directed graphs

### Priorities

Test (eval) driven development, repeatability, debuggability, and telemetry are **CRITICAL** for rapid iteration and development of Agentic applications.

Junjo prioritizes the following capabilities above all else to ensure these things are not an afterthought. 

1. Eval driven development / Test driven development with pytest
1. Telemetry
1. Visualization
1. Type safety (pydantic)
1. Concurrency safe (asyncio)


## Contributing

This project was made with the [uv](https://github.com/astral-sh/uv) python package manager.

```bash
# Setup and activate the virtual environment
$ uv venv .venv
$ source .venv/bin/activate

# Install optional development dependencies
$ uv pip install -e ".[dev,graphviz]"
```

### Graphviz

<mark>Currently Broken</mark>

This project can render junjo Graph objects as images. However, it requires [Graphviz](https://graphviz.org/) to be installed on the underlying system (your developer computer or the docker image).

```bash
# Install Graphvis on MacOS with homebrew
$ brew install graphviz
```

```python
# Generate an image from a Graph
from junjo.graphviz.utils import graph_to_graphviz_image
graph_to_graphviz_image(workflow_graph)
```

### Code Linting and Formatting

This project utilizes [ruff](https://astral.sh/ruff) for linting and auto formatting. The VSCode settings.json in this project helps with additional formatting.

- [Ruff VSCode Extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)

### Building The Sphinx Docs

```bash
# 1. ensure optional development dependencies are installed (see above)
# 2. ensure the virtual environment is activated (see above)

# Execute the build command to preview the new docs.
# They will appear in a .gitignored folder docs/_build
$ sphinx-build -b html docs docs/_build
```

## Code Generation

### Protobuf schema generation

1. Requires the optional `dev` dependencies to be installed via `uv pip install -e ".[dev]"`
2. Requires [protoc](https://grpc.io/docs/protoc-installation/) which can be installed into your developer environment host machine ([instructions](https://grpc.io/docs/protoc-installation/)).
3. Copy the .proto files from the junjo-server project to `src/telemetry/junjo_server/proto`
4. Run `make proto` from the project root to generate the `proto_gen` files for the client
5. Update any required changes to the `src/telemetry/junjo_server/client.py` file (type changes, fields, etc.)