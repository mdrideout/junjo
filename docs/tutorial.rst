.. _tutorial:

##############################################################
Tutorial: Building Your First Workflow
##############################################################

.. meta::
    :description: A step-by-step tutorial on building your first Junjo workflow. Learn how to define state, create a store, build nodes, and assemble a graph.
    :keywords: junjo, python, workflow, tutorial, getting started, state management, node, graph

This tutorial will guide you through the process of building a simple Junjo workflow from scratch. We will build the same workflow that is in the :doc:`getting_started` guide, but we will do it step-by-step to better understand how each component works.

Step 1: Define the State
========================

First, we need to define the shape of our workflow's state. We'll use a Pydantic model that inherits from `BaseState`.

.. code-block:: python

    from junjo import BaseState

    class SampleWorkflowState(BaseState):
        count: int | None = None
        items: list[str]

Step 2: Create the Store
========================

Next, we'll create a `BaseStore` to manage our state. This store will have one action, `set_count`, which we'll use to update the `count` field in our state.

.. code-block:: python

    from junjo import BaseStore

    class SampleWorkflowStore(BaseStore[SampleWorkflowState]):
        async def set_count(self, payload: int) -> None:
            await self.set_state({"count": payload})

Step 3: Create the Nodes
========================

Now, let's create the nodes that will perform the work of our workflow. We'll create five nodes:

- `FirstNode`: The entry point of our workflow.
- `CountItemsNode`: Counts the items in the state and updates the `count`.
- `EvenItemsNode`: A node that will be executed if the count is even.
- `OddItemsNode`: A node that will be executed if the count is odd.
- `FinalNode`: The exit point of our workflow.

.. code-block:: python

    from junjo import Node

    class FirstNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            print("First Node Executed")

    class CountItemsNode(Node[SampleWorkflowStore]):
        async def service(self, store: SampleWorkflowStore) -> None:
            state = await store.get_state()
            items = state.items
            count = len(items)
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

Step 4: Create the Condition
============================

We need a `Condition` to create a branch in our workflow. This condition will check if the `count` in our state is even.

.. code-block:: python

    from junjo import Condition

    class CountIsEven(Condition[SampleWorkflowState]):
        def evaluate(self, state: SampleWorkflowState) -> bool:
            count = state.count
            if count is None:
                return False
            return count % 2 == 0

Step 5: Assemble the Graph in a Factory
=======================================

Now we'll bring everything together in a `Graph`. We'll create a `graph_factory` function that instantiates all of our nodes and assembles them into a `Graph`.

.. code-block:: python

    from junjo import Edge, Graph

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
            sink=final_node,
            edges=[
                Edge(tail=first_node, head=count_items_node),
                Edge(tail=count_items_node, head=even_items_node, condition=CountIsEven()),
                Edge(tail=count_items_node, head=odd_items_node),
                Edge(tail=even_items_node, head=final_node),
                Edge(tail=odd_items_node, head=final_node),
            ]
        )

Step 6: Create and Execute the Workflow
=======================================

Finally, we'll create a `Workflow` instance and execute it. We'll pass our `graph_factory` and a `store_factory` to the `Workflow` constructor. The `store_factory` will create a new instance of our `SampleWorkflowStore` with some initial data.

.. code-block:: python

    from junjo import Workflow
    import asyncio

    async def main():
        # Create the workflow
        sample_workflow = Workflow[SampleWorkflowState, SampleWorkflowStore](
            name="Getting Started Example Workflow",
            graph_factory=create_graph,
            store_factory=lambda: SampleWorkflowStore(
                initial_state=SampleWorkflowState(
                    items=["laser", "coffee", "horse"]
                )
            )
        )

        # Execute the workflow
        await sample_workflow.execute()
        print("Final state: ", await sample_workflow.get_state_json())

    if __name__ == "__main__":
        asyncio.run(main())

Congratulations! You've built your first Junjo workflow. You can now run this file and see the output in your console.