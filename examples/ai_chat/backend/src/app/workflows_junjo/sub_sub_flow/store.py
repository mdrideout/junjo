
from junjo.store import BaseStore

from app.workflows_junjo.sub_sub_flow.state import SubSubFlowState


class SubSubFlowStore(BaseStore[SubSubFlowState]):
    """
    A concrete store for SubSubFlowState.
    """

    async def append_fact(self, payload: str) -> None:
        await self.set_state({"facts": [*self._state.facts, payload]})

