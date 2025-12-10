"""Workflow definitions based on getting_started example."""

import random

from junjo import BaseState, BaseStore, Condition, Edge, Graph, Node, Workflow
from lorem_text import lorem


# Define the workflow state
class SampleWorkflowState(BaseState):
    count: int | None = None  # Does not need an initial state value
    items: list[str]  # Does need an initial state value
    context: str | None = None  # Simulated RAG context (~500 words)


# Define the workflow store
class SampleWorkflowStore(BaseStore[SampleWorkflowState]):
    # An immutable state update function
    async def set_count(self, payload: int) -> None:
        await self.set_state({"count": payload})

    async def set_context(self, payload: str) -> None:
        await self.set_state({"context": payload})


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


class AddRandomNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        # Add a random number to the count
        state = await store.get_state()
        random_num = random.randint(1, 100)
        new_count = (state.count or 0) + random_num

        await store.set_count(new_count)
        print(f"Added {random_num} to count, new count: {new_count}")


class EvenItemsNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Path taken for even items count.")


class OddItemsNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Path taken for odd items count.")


class SimulatedRagResponse(Node[SampleWorkflowStore]):
    """Simulates a RAG retrieval response with ~500 words of context."""

    async def service(self, store: SampleWorkflowStore) -> None:
        # Generate ~500 words of lorem ipsum to simulate RAG context
        context = lorem.words(500)
        await store.set_context(context)
        print(f"Simulated RAG response: {len(context)} chars, ~500 words")


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
    simulated_rag_node = SimulatedRagResponse()
    count_items_node = CountItemsNode()
    add_random_node = AddRandomNode()
    even_items_node = EvenItemsNode()
    odd_items_node = OddItemsNode()
    final_node = FinalNode()

    # Create the workflow graph
    return Graph(
        source=first_node,
        sink=final_node,
        edges=[
            Edge(tail=first_node, head=simulated_rag_node),
            Edge(tail=simulated_rag_node, head=count_items_node),
            Edge(tail=count_items_node, head=add_random_node),
            # Branching based on the count (after random added)
            Edge(
                tail=add_random_node,
                head=even_items_node,
                condition=CountIsEven(),
            ),  # Only transitions if count is even
            Edge(
                tail=add_random_node, head=odd_items_node
            ),  # Fallback if first condition is not met
            # Branched paths converge to the final node
            Edge(tail=even_items_node, head=final_node),
            Edge(tail=odd_items_node, head=final_node),
        ],
    )


def create_workflow(items: list[str]) -> Workflow[SampleWorkflowState, SampleWorkflowStore]:
    """
    Create a workflow instance with the given items.

    Args:
        items: List of items for the workflow state

    Returns:
        Configured Workflow instance
    """
    return Workflow[SampleWorkflowState, SampleWorkflowStore](
        name="E2E Test Workflow",
        graph_factory=create_graph,
        store_factory=lambda: SampleWorkflowStore(
            initial_state=SampleWorkflowState(items=items)
        ),
    )
