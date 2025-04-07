
from junjo.node import Node
from junjo.store import BaseStore

from app.workflows_junjo.test_sub_flow.state import TestSubFlowState


class TestSubFlowStore(BaseStore[TestSubFlowState]):
    """
    A concrete store for TestSubFlowState.
    """

    async def append_joke(self, node: Node, payload: str) -> None:
        await self.set_state(node, {"jokes": [*self._state.jokes, payload]})

