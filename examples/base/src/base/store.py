from typing import Any

from junjo.state import BaseState
from junjo.store import BaseStore


class MyGraphState(BaseState):
    items: list[str]
    counter: int
    warning: bool

class MyGraphStore(BaseStore[MyGraphState]):
    """
    A concrete store for MyGraphState.
    """

    def increment(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter + 1})

    def decrement(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter - 1})

    def set_counter(self, payload: int) -> MyGraphState:
        return self._state.model_copy(update={"counter": payload})

    def set_warning(self, payload: bool) -> MyGraphState:
        return self._state.model_copy(update={"warning": payload})

    def add_ten(self, payload: Any = None):
        return self._state.model_copy(update={"counter": self._state.counter + 10})
