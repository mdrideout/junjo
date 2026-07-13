from junjo import Node

from base.sample_workflow.nodes.count_items_node.service import count_items
from base.sample_workflow.store import SampleWorkflowStore


class CountItemsNode(Node[SampleWorkflowStore]):
    """Workflow node that counts items"""

    async def service(self, store: SampleWorkflowStore) -> None:
        # Get the current state
        state = await store.get_state()
        print("Running CountNode service from initial state: ", state.model_dump())

        items = state.items
        count = await count_items(items)
        print("Counted items: ", count)

        # Update the store with the new count
        await store.set_counter(count)
        return
