# Junjo 順序

> Japanese Translation: order, sequence, procedure

Junjo is a modern Python library for designing, executing, testing, and debugging complex, graph-based AI workflows.

Whether you’re building a simple chatbot, a complex data manipulation pipeline, or a sophisticated workflow with dynamic branching and parallel execution, Junjo provides the tools to define your logic as a clear graph of nodes and edges.

#### Docs

- [Python API Docs](https://python-api.junjo.ai/)
- [PyPI](https://pypi.org/project/junjo/)

#### Benefits:

- Asyncio & Pydantic native
- Visualize your AI workflows
- Build in redux-inspired state machine
- Create robust and predictable conditional chains of LLM calls
- Organize complex workflow executions into a scalable clean Graph structure
- Manage execution order, loops, and concurrency
- Supports Eval-Driven Development techniques
  - Test every node of your workflow to 100% evaluation accuracy
  - Test your workflows with dozens or thousands of input cases
  - Rapidly iterate on your AI capabilities knowing for sure you're making progress
- Native opentelemetry support for clear tracing, observability, and debugging
  - Try our **optional, free, open source** companion [junjo-server](https://github.com/mdrideout/junjo-server) telemetry server.

<img src="https://raw.githubusercontent.com/mdrideout/junjo/main/junjo-screenshot.png" width="600" />

_junjo-screenshot.png_

#### Decoupled

Junjo doesn't change how you create AI / LLM calls. Use any AI or LLM service provider or library. Junjo simply helps you organize your python functions into a clean organized graph structure with predictable, testable execution.

Junjo provides the building blocks that let you make any sort of executable workflow. From linear function calls, to complex branching workflows with concurrent sublfows, to fully autonomous agents.

> 
> There are zero proprietary AI / LLM implementations in Junjo. Use whatever LLM library you want.
> 
> All logs produced are opentelemetry compatible. Existing otel spans are annotated with workflow and node execution span wrappers.
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

# Install optional development dependencies (graphviz is optional for running the graphviz visualizer)
# Graphviz, if utilized, must also be installed on the host system (see below)
$ uv pip install -e ".[dev,graphviz]"
```

## Visualizing Your Workflows

### Junjo Server

[Junjo Server](https://github.com/mdrideout/junjo-server) is an optional, free, open-source companion telemetry server that can ingest OpenTelemetry traces from Junjo, and visualize the workflow execution graph structures.

The user interface makes it easy to observe and debug workflow executions. Step through every single state machine update to see how data changes throughout the workflow's lifecycle. 

### Graphviz

Junjo can render workflow graphs as images. It requires [Graphviz](https://graphviz.org/) to be installed on the underlying system (your developer computer or the docker image), as well as the above optional graphviz development dependencies in this python library.

```bash
# Install Graphviz on MacOS with homebrew
$ brew install graphviz
```

```python
# visualize.py
from base.sample_workflow.workflow import sample_workflow_graph

def main():
    # Every graph can execute .export_graphviz_assets() to generate all graphs and subflow graphs in a workflow
    # Creates .svg renderings, .dot notation files, and an HTML template to render the graphs
    sample_workflow_graph.export_graphviz_assets()

if __name__ == "__main__":
    main()
```

```bash
# Run the visualizer
python -m src.base.visualize
```

<img src="https://raw.githubusercontent.com/mdrideout/junjo/main/junjo-screenshot-graphviz.png" width="600" />

#### Full Example
**See the full example inside `examples/base`.**

## Contributing

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

