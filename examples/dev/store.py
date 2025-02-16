from typing import Any

from pydantic import BaseModel

from junjo.store.store import BaseStore, state_action


class GraphState(BaseModel):
    counter: int = 0
    loading: bool = False

class GraphStore(BaseStore[GraphState]):
    """
    A concrete store for GraphState.
    """

    @property
    def initial_state(self) -> GraphState:
        return GraphState(counter=0, loading=False)

    @state_action
    def increment(self, payload: Any = None) -> GraphState:
        return self._state.model_copy(update={"counter": self._state.counter + 1})

    @state_action
    def decrement(self, payload: Any = None) -> GraphState:
        return self._state.model_copy(update={"counter": self._state.counter - 1})

    @state_action
    def set_counter(self, payload: int) -> GraphState:
        return self._state.model_copy(update={"counter": payload})

    @state_action
    def set_loading(self, payload: bool) -> GraphState:
        return self._state.model_copy(update={"loading": payload})

    @state_action
    def add_ten(self, payload: Any = None):
        return self._state.model_copy(update={"counter": self._state.counter + 10})
