from typing import Any

from pydantic import BaseModel

from junjo.store import BaseStore, immutable_update


class MyGraphState(BaseModel):
    items: list[str]
    counter: int
    warning: bool

class MyGraphStore(BaseStore[MyGraphState]):
    """
    A concrete store for MyGraphState.
    """

    @immutable_update
    def increment(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter + 1})

    @immutable_update
    def decrement(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter - 1})

    @immutable_update
    def set_counter(self, payload: int) -> MyGraphState:
        return self._state.model_copy(update={"counter": payload})

    @immutable_update
    def set_warning(self, payload: bool) -> MyGraphState:
        return self._state.model_copy(update={"warning": payload})

    @immutable_update
    def add_ten(self, payload: Any = None):
        return self._state.model_copy(update={"counter": self._state.counter + 10})
