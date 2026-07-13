from junjo import Node

from base.sample_workflow.store import SampleWorkflowStore


class AddTenNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        await store.add_ten()
        return
