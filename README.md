# Junjo

A simply python agentic graph execution framework optimized for telemetry and visualization.

#### Why?

Agentic applications use LLMs to determine the order of execution of python functions. These functions may involve LLM requests, API requests, database CRUD operations, etc.

The simplest way to organize functions that can be / need to be executed in a certain order is in the form of a directed graph.

A directed graph gives one the building blocks to create any sort of agentic application, including:

- High precision agentic workflows in the form of a Directed Acyclic Graph (DAG)
- Autonomous AI Agents in the form of dynamically determined Directed Graphs

#### Alternatives

Alternative python graph execution libraries are too complex. They are great libraries, but with steep learning curves.

- [Burr](https://burr.dagworks.io/) is a highly functional and competetnt graph execution and state machine framework. However, it has problematic asyncio and pydantic implementations. The way concurrency works is highly proprietary and confusing. The telemetry layer is also too proprietary.
- [PydanticAI Graphs](https://ai.pydantic.dev/graph/) is a newer framework that seems to fix a lot of the early architecture decisions made at Burr. However, it over-complicates graph concepts, and its proprietary PydanticAI telemetry layer for [LogFire](https://pydantic.dev/logfire) is not optimal for visualizing and debugging graphs.

Junjo tries to leverage conventional approachs to directed graphs and finite state machines to avoid any proprietary concepts. 

### Priorities

Test (eval) driven development, repeatability, debuggability, and telemetry are **CRITICAL** for rapid iteration and development of Agentic applications.

Junjo prioritizes the following capabilities above all else to ensure these things are not an afterthought. 

1. Eval driven development / Test driven development with pytest
1. Telemetry
1. Visualization
1. Type safety (pydantic)
1. Asyncio and concurrency


# Contributing

This project was made with the [uv](https://github.com/astral-sh/uv) python package manager in place of pip.

```bash
# Setup and activate the virtual environment
$ uv venv .venv
$ source .venv/bin/activate

# Install optional development dependencies
$ uv pip install -e ".[dev,graphviz]"
```

### Graphviz

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