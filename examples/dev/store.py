from typing import Any

from pydantic import BaseModel

from junjo.store.store import BaseStore, state_action


class MyGraphState(BaseModel):
    items: list[str]
    counter: int
    warning: bool

class MyGraphStore(BaseStore[MyGraphState]):
    """
    A concrete store for MyGraphState.
    """

    @state_action
    def increment(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter + 1})

    @state_action
    def decrement(self, payload: Any = None) -> MyGraphState:
        return self._state.model_copy(update={"counter": self._state.counter - 1})

    @state_action
    def set_counter(self, payload: int) -> MyGraphState:
        return self._state.model_copy(update={"counter": payload})

    @state_action
    def set_warning(self, payload: bool) -> MyGraphState:
        return self._state.model_copy(update={"warning": payload})

    @state_action
    def add_ten(self, payload: Any = None):
        return self._state.model_copy(update={"counter": self._state.counter + 10})
