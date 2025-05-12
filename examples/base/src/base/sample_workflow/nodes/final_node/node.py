from junjo import Node

from base.sample_workflow.store import SampleWorkflowStore


class FinalNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Running the final node.")
        return
