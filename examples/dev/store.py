from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from junjo.store.store import StateStore


# 1) Define your Enum for action names
class GraphStateActions(StrEnum):
    INCREMENT = "increment"
    DECREMENT = "decrement"
    SET_COUNTER = "set_counter"
    SET_LOADING = "set_loading"

# 2) Define your state
class GraphState(BaseModel):
    counter: int = 0
    loading: bool = False

# 3) Create a concrete store
class GraphStore(StateStore[GraphState, GraphStateActions]):
    @property
    def name(self) -> str:
        return "graphState"

    @property
    def initial_state(self) -> GraphState:
        return GraphState(counter=0, loading=False)

    @property
    def reducers(self):
        def increment(state: GraphState, payload: Any) -> GraphState:
            return state.model_copy(update={"counter": state.counter + 1})

        def decrement(state: GraphState, payload: Any) -> GraphState:
            return state.model_copy(update={"counter": state.counter - 1})

        def set_counter(state: GraphState, payload: int) -> GraphState:
            return state.model_copy(update={"counter": payload})

        def set_loading(state: GraphState, payload: bool) -> GraphState:
            return state.model_copy(update={"loading": payload})

        return {
            GraphStateActions.INCREMENT: increment,
            GraphStateActions.DECREMENT: decrement,
            GraphStateActions.SET_COUNTER: set_counter,
            GraphStateActions.SET_LOADING: set_loading,
        }

