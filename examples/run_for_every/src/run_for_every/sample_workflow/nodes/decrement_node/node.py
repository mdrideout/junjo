from junjo import Node

from run_for_every.sample_workflow.store import SampleWorkflowStore


class DecrementNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        await store.decrement()
        return
