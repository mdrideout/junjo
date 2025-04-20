
from junjo.store import BaseStore

from app.workflows_junjo.concurrent_sub_flow.state import ConcurrentSubFlowState


class ConcurrentSubFlowStore(BaseStore[ConcurrentSubFlowState]):
    """
    A concrete store for ConcurrentSubFlowState.
    """

    async def append_poem(self, payload: str) -> None:
        await self.set_state({"poems": [*self._state.poems, payload]})

