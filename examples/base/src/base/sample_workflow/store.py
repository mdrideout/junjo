from typing import Any

from junjo.state import BaseState
from junjo.store import BaseStore


class SampleWorkflowState(BaseState):
    items: list[str]
    counter: int
    decision: int | None = None
    joke: str | None = None
    fact: str | None = None

class SampleWorkflowStore(BaseStore[SampleWorkflowState]):


    async def increment(self) -> None:
        await self.set_state({"counter": self._state.counter + 1})

    async def decrement(self) -> None:
        await self.set_state({"counter": self._state.counter - 1})

    async def set_counter(self, payload: int) -> None:
        await self.set_state({"counter": payload})

    async def add_ten(self, payload: Any = None) -> None:
        await self.set_state({"counter": self._state.counter + 10})

    async def set_decision(self, payload: int) -> None:
        await self.set_state({"decision": payload})

    async def set_joke(self, payload: str) -> None:
        await self.set_state({"joke": payload})

    async def set_fact(self, payload: str) -> None:
        await self.set_state({"fact": payload})
