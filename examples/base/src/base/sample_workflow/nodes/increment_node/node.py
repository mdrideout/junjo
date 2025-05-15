from junjo import Node

from base.sample_workflow.store import SampleWorkflowStore


class IncrementNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        await store.increment()
        return
