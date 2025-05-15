from junjo import Node

from base.sample_workflow.store import SampleWorkflowStore


class ExactPathNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Running the exact path node.")
        return
