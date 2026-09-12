---
title: "Junjo Python SDK quickstart"
description: "Install Junjo, run a small Python workflow, then connect execution telemetry and evaluation targets to Junjo AI Studio."
---
<!-- migrated-from: sdks/python/docs/getting_started.rst; source-hash: sha256:457b15516ca53dca2c05633f35cd0d0f68c54eec1cc64980128310ab2e5ef379 -->

<a id="getting-started"></a>
This quickstart introduces the SDK's graph and state building blocks with a
provider-free example. It runs in your Python environment; it does not deploy
Studio or configure telemetry by itself.

If you already have an AI application, begin with
[recursive self improvement](/docs/recursive-self-improvement/) or the
[OpenAI Agents SDK integration](/docs/python/integrations/openai-agents/).
You can add observability and evaluation without replacing the outer framework.

## Installation

Junjo Python Library Installation:

```bash
# With pip
pip install junjo

# With poetry
poetry add junjo

# With uv
uv add junjo
```

## Basic Usage

The following is a basic, single file example of how to use Junjo to create a simple workflow. This example demonstrates the basic concepts of defining a workflow, creating nodes and edges, and executing the workflow.

The example counts items and selects a conditional path. These same building
blocks can separate retrieval, policy checks, and synthesis in an AI workflow.

More advanced examples can be found in the [examples directory](https://github.com/mdrideout/junjo/tree/master/sdks/python/examples) of the Junjo repository.

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

## See the execution in Studio

1. [Start Junjo AI Studio](/docs/studio/deployment/) and create an application
   telemetry API key in **API Keys**.
2. Add the [OpenTelemetry setup](/docs/observability/opentelemetry/#complete-configuration-example)
   to the application's entrypoint. Initialize it once before `main()` runs and
   shut it down when the application exits.
3. Run this example again. In Studio, locate **Getting Started Example Workflow**
   and match its execution to `result.run_id`. Inspect the count update and the
   even/odd path. A local flush alone does not prove Studio received the trace.

## Evaluate a change

Use a `WorkflowTarget` to evaluate the final count and `NodeTarget` to focus on
one operation. Ask your coding agent to add representative empty, even, and odd
input cases, establish a baseline, then compare a changed implementation against
the same locked dataset. The [evaluation guide](/docs/python/evaluation/)
owns the harness declaration, separate developer access token, and run commands.

For a step-by-step explanation of the code above, continue to
[Build your first Junjo workflow](/docs/python/tutorial/).
