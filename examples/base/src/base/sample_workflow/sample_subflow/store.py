
from junjo import BaseState, BaseStore


class SampleSubflowState(BaseState):
    """
    Sample subflow state.

    Will inherit items from the parent workflow store.
    """
    items: list[str] | None = None
    joke: str | None = None
    fact: str | None = None

class SampleSubflowStore(BaseStore[SampleSubflowState]):

    async def set_items(self, payload: list[str]) -> None:
        await self.set_state({"items": payload})

    async def set_joke(self, payload: str) -> None:
        await self.set_state({"joke": payload})

    async def set_fact(self, payload: str) -> None:
        await self.set_state({"fact": payload})
