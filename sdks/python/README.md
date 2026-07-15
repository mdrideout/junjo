# Junjo Python SDK

> 順序 (junjo): order, sequence, procedure

Junjo is a modern Python library for designing, executing, testing, and
debugging explicit graph Workflows and bounded, provider-neutral Agents.

Use a Workflow when the application knows the possible procedure in advance,
and an Agent when a model must choose among an explicit set of typed Tools at
runtime. Both execution modes remain isolated, testable, and observable.

#### Docs

- [Python SDK Docs](https://junjo.ai/docs/python/)
- [PyPI](https://pypi.org/project/junjo/)

#### Python support

Junjo requires Python 3.11 or newer. Development and documentation use Python
3.13, while CI currently verifies compatibility across Python 3.11 through
3.14.

#### Benefits:

- ✨ Visualize your AI workflows
- 🧭 Inspect dynamic Agent model and Tool operation timelines
- 🧠 Redux inspired state management and state debugging tools
- ⚡️ Concurrency and type safety native with asyncio and pydantic
- 🔗 Organize conditional chains of LLM calls into observable graph workflows
- 🏎️ Easy patterns for directed graph loops, branching, and concurrency
- 🧪 Eval-Driven Development focused
  - Build massive eval sets by mocking node state
  - Programmatically build and update eval sets with agentic code assistants
  - Eval patterns are based on pytest, leveraging its testing framework and capabilities
  - Rapidly iterate on your AI capabilities and avoid regressions
- 🔭 OpenTelemetry native
  - Provides organized, structured traces to any OpenTelemetry provider
  - Companion open source **[Junjo AI Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio)** enhances debugging and evaluation of production data


<center>
<b>Junjo AI Studio Screenshot</b>
<img src="https://raw.githubusercontent.com/mdrideout/junjo/master/sdks/python/junjo-screenshot.png" width="1000" />
</center>


## Junjo's Philosophy

#### 🔍 Transparency

Junjo strives to be the opposite of a "black box". Transparency, observability, eval driven development, and production data debugging are requirements for AI applications handling mission critical data, that need repeatable and high accuracy chained LLM logic.

#### ⛓️‍💥 Decoupled

Junjo doesn't change how you implement LLM providers or make calls to their services.

Continue using [google-genai](https://github.com/googleapis/python-genai), [openai-python](https://github.com/openai/openai-python), [grok / xai sdk](https://github.com/xai-org/xai-sdk-python), [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python), [LiteLLM](https://github.com/BerriAI/litellm) or even REST API requests to any provider.

Junjo remains decoupled from LLM providers. There are no proprietary implementations, no hijacking of python docstrings, no confusing or obfuscating decorators, and no middleman proxies.

Junjo helps you organize Python functions—whether they perform logic, model
calls, retrieval, or application I/O—into predictable, testable, and
observable Workflow and Agent executions.

#### 🥧 Conventional

Junjo provides primitive building blocks for explicit graph Workflows, from
linear chains of LLM calls to conditional loops, branching paths, and
concurrent subflows. A Workflow declares its possible graph paths before
execution; model calls inside Nodes may update state used by edge conditions,
but they do not dynamically create or rewrite the graph.

Junjo also provides a first-class `Agent` execution model for the complementary
case where a model chooses the next capability at runtime from an explicit set
of typed Tools. An Agent is a sibling to `Workflow`, not a dynamically
generated graph or a special kind of Workflow.

Junjo uses conventional Pythonic architecture. Rather than obfuscating,
proprietary decorators or runtime scripts that hijack execution, Workflows use
explicit Python Graph primitives and Agents use ordinary typed definitions,
bindings, and Tools. Pydantic owns the declared data boundaries.

State is modeled after the conventional [Elm Architecture](https://guide.elm-lang.org/architecture/), and inspired by [Redux](https://redux.js.org/) for clean separation of concerns, concurrency safety, and debuggability.

This helps language servers and coding agents understand large Junjo
applications without learning proprietary, hidden execution patterns.

Junjo organizes conventional OpenTelemetry spans into understandable execution
evidence. Your existing OpenTelemetry provider continues to work, while
[Junjo AI Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio)
adds specialized Workflow graphs, Agent timelines, Store reconstruction, and
evidence-integrity diagnostics.

#### 🤝 Compatible

Junjo can work alongside external AI Agent frameworks. Application code can
expose a Junjo Workflow to one of those frameworks as a **tool** for a
high-accuracy, repeatable process such as RAG retrieval or complex document
parsing. That adapter does not turn the Workflow itself into an Agent.

You can execute autonomous agent capabilities from other libraries inside a Junjo AI workflow. For example, a Junjo workflow node can run a [smolagents](https://github.com/huggingface/smolagents) tool calling agent as a single step within a greater Junjo workflow or subflow.

## Code Examples

_**Find several example Junjo applications inside the [examples](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples) directory in this repository.**_

- [AI Chat](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/ai_chat) - a live-model FastAPI and React application demonstrating model-powered Workflows, bounded Agents, versioned persistence, Studio diagnostics, and eval-driven development.
- [Getting Started](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/getting_started) - the basis of our getting started documentation
- [Base Example](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/base) - a minimal python example showcasing several Junjo patterns

### Getting Started Code

This is a single-file implementation of a basic Junjo powered python application. See the [getting started](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples/getting_started) directory for dependencies, requirements, and instructions to run this.

```python

from junjo import BaseState, BaseStore, Condition, Edge, Graph, Node, Workflow

# Run With
# python -m main
# uv run -m main

async def main():
    """The main entry point for the application."""

    # Define the workflow state
    class SampleWorkflowState(BaseState):
        count: int | None = None # Does not need an initial state value
        items: list[str] # Does need an initial state value

    # Define the workflow store
    class SampleWorkflowStore(BaseStore[SampleWorkflowState]):
        # An immutable state update function
        async def set_count(self, payload: int) -> None:
            await self.set_state({"count": payload})

    # Define the nodes
    class FirstNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            print("First Node Executed")

    class CountItemsNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            # Get the state and count the items
            state = await store.get_state()
            items = state.items
            count = len(items)

            # Perform a state update with the count
            await store.set_count(count)
            print(f"Counted {count} items")

    class EvenItemsNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            print("Path taken for even items count.")

    class OddItemsNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            print("Path taken for odd items count.")

    class FinalNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            print("Final Node Executed")

    class CountIsEven(Condition[SampleWorkflowState]):
        def evaluate(self, state: SampleWorkflowState) -> bool:
            count = state.count
            if count is None:
                return False
            return count % 2 == 0

    def create_graph() -> Graph:
        """
        Factory function to create a new instance of the sample workflow graph.
        This ensures that each workflow execution gets a fresh, isolated graph,
        preventing state conflicts in concurrent environments.
        """
        # Instantiate the nodes
        first_node = FirstNode()
        count_items_node = CountItemsNode()
        even_items_node = EvenItemsNode()
        odd_items_node = OddItemsNode()
        final_node = FinalNode()

        # Create the workflow graph
        return Graph(
            source=first_node,
            sinks=[final_node],
            edges=[
                Edge(tail=first_node, head=count_items_node),

                # Branching based on the count of items
                Edge(tail=count_items_node, head=even_items_node, condition=CountIsEven()), # Only transitions if count is even
                Edge(tail=count_items_node, head=odd_items_node), # Fallback if first condition is not met

                # Branched paths converge to the final node
                Edge(tail=even_items_node, head=final_node),
                Edge(tail=odd_items_node, head=final_node),
            ]
        )

    def create_workflow() -> Workflow[SampleWorkflowState, SampleWorkflowStore]:
        """
        Helper function to build the workflow used in this example.
        """
        return Workflow[SampleWorkflowState, SampleWorkflowStore](
            name="Getting Started Example Workflow",
            graph_factory=create_graph,
            store_factory=lambda: SampleWorkflowStore(
                initial_state=SampleWorkflowState(
                    items=["laser", "coffee", "horse"]
                )
            )
        )

    # Create and execute the workflow
    workflow = create_workflow()
    result = await workflow.execute()
    print("Final state: ", result.state.model_dump_json())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Building Explicit Graph Workflows for AI Systems

AI applications often need to coordinate Python functions that perform LLM
requests, API calls, database operations, retrieval, and deterministic business
logic.

Junjo Workflows organize those functions as an explicit
[directed graph](https://en.wikipedia.org/wiki/Directed_graph). The application
declares the possible paths before execution. Nodes perform work and update
typed state; edges and conditions determine which declared path a run takes.
This produces a bounded structure that is straightforward to inspect, test,
and observe.

The current Workflow runtime supports structures such as:

- High precision workflows in the form of a Directed Acyclic Graph (DAG)
- Conditional branches and loops over declared edges
- Concurrent node groups and nested subflows

The Junjo Agent runtime covers bounded runtime Tool selection without
pretending that the realized sequence of model and Tool operations is a static
or dynamically generated Workflow graph. Workflows and Agents compose through
ordinary application Nodes and Tools while retaining independent state,
limits, and diagnostics.

## Junjo AI Studio

[Junjo AI Studio](https://github.com/mdrideout/junjo/tree/master/apps/studio) is our open source companion telemetry and debugging platform. It ingests Junjo's OpenTelemetry spans, providing execution visualizations and step-by-step debugging of state changes made by LLMs.

**Quick Start:**

```bash
# Start from the Junjo AI Studio - Minimal Build template repository
git clone https://github.com/mdrideout/junjo-ai-studio-minimal-build.git
cd junjo-ai-studio-minimal-build

# Configure environment
cp .env.example .env

# Start services
docker compose up -d

# Access the UI at http://localhost:26153
```

**Features:**
- Interactive graph visualization with execution path tracking
- Dynamic Agent operation timelines with normalized model and Tool evidence
- Verified Workflow and Agent Store state navigation
- Evidence-integrity diagnostics and nested executable navigation
- Multi-execution comparison

**Architecture:** Three-service Docker setup (backend, ingestion service, frontend) that runs on minimal resources (1GB RAM, shared vCPU).

See the [Junjo AI Studio documentation](https://junjo.ai/docs/studio/overview/) for complete setup and configuration.

**Example Repositories:**

- [Junjo AI Studio - Minimal Build](https://github.com/mdrideout/junjo-ai-studio-minimal-build) - a docker compose environment of the essential Junjo AI Studio services.
- [Junjo AI Studio - Deployment Example](https://github.com/mdrideout/junjo-ai-studio-deployment-example) - a production VM ready deployment example, including Caddy reverse proxy and SSL certificate handling.


## Graphviz

Junjo can render workflow graphs as images with Graphviz. Install Graphviz on
the host system, then call `Graph.export_graphviz_assets()` on the graph you
want to visualize.

```bash
# Install Graphviz on MacOS with homebrew
$ brew install graphviz
```

```python
# visualize.py
from base.sample_workflow.graph import create_sample_workflow_graph

def main():
    # Every graph can execute .export_graphviz_assets() to generate all graphs and subflow graphs in a workflow
    # Creates .svg renderings, .dot notation files, and an index.html gallery page that displays the rendered graphs
    create_sample_workflow_graph().export_graphviz_assets()

if __name__ == "__main__":
    main()
```

```bash
# Run the visualizer
$ cd examples/base
$ uv run --package base -m base.visualize
```

<center>
<b>Screenshot: Graphviz visualized Junjo workflow and subflow</b>
<img src="https://raw.githubusercontent.com/mdrideout/junjo/master/sdks/python/junjo-screenshot-graphviz.png" width="1000" />
</center>


## Contributing

This project was made with the [uv](https://github.com/astral-sh/uv) python package manager.

```bash
# From the Junjo platform repository root
$ cd sdks/python

# Setup and activate the virtual environment
$ uv venv --python 3.13 .venv
$ source .venv/bin/activate

# Install optional development dependencies
# Graphviz, if utilized, must also be installed on the host system (see above)
# Option 1:
$ uv pip install -e ".[dev]"

# Option 2:
$ uv sync --package junjo --extra dev
```

### Code Linting and Formatting

This project utilizes [ruff](https://astral.sh/ruff) for linting and auto formatting. The VSCode settings.json in this project helps with additional formatting.

- [Ruff VSCode Extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)

### Validating The API Documentation

```bash
# Validate the explicit public surface and render it with Griffe.
$ uv run python docs/export_api.py validate
```

### Tests

```bash
# Run the tests with uv
$ uv run pytest
```
