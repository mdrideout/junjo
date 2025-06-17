from junjo import Node

from run_for_every.sample_workflow.store import SampleWorkflowStore


class EvenPathNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Running the even path node.")
        return
