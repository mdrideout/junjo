---
title: "Getting Started"
---
<!-- migrated-from: sdks/python/docs/getting_started.rst; source-hash: sha256:457b15516ca53dca2c05633f35cd0d0f68c54eec1cc64980128310ab2e5ef379 -->

<a id="getting-started"></a>
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

<img src="/docs-assets/generated/python/junjo-base-example-screenshot.png" alt="Example telemetry visualization of the getting started example" style="max-width: 100%; width: 100%; display: block; margin-inline: auto" />

*The above screenshot shows the telemetry visualization of this getting started example. Visually step through the workflow nodes and individual state updates.*

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
