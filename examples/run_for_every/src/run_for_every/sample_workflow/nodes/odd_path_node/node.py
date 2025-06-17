from junjo import Node

from run_for_every.sample_workflow.store import SampleWorkflowStore


class OddPathNode(Node[SampleWorkflowStore]):
    async def service(self, store: SampleWorkflowStore) -> None:
        print("Running the odd path node.")
        return
