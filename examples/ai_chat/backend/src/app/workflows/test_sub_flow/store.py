
from junjo.store import BaseStore

from app.workflows.test_sub_flow.state import TestSubFlowState


class TestSubFlowStore(BaseStore[TestSubFlowState]):
    """
    A concrete store for TestSubFlowState.
    """

    async def append_joke(self, payload: str) -> None:
        await self.set_state({"jokes": [*self._state.jokes, payload]})

    async def set_subflow_facts(self, payload: list[str]) -> None:
        await self.set_state({"subflow_facts": payload})

