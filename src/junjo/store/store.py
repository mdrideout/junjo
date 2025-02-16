import abc
from collections.abc import Callable, Iterable
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

# -----------------------------------------
# Type Definitions
# -----------------------------------------
StateT = TypeVar("StateT", bound=BaseModel)
ActionEnumT = TypeVar("ActionEnumT", bound=Enum)

# A reducer has the signature: (state, payload) -> new_state
Reducer = Callable[[StateT, Any], StateT]

# A generic type alias that takes two type parameters
# ActionMap: TypeAlias = dict[ActionEnumT, Reducer]
Subscribers = list[Callable[[StateT], None]]

class _BaseStore(Generic[StateT, ActionEnumT]):
    """
    A minimal, Redux-like store for a Pydantic state, with typed Enum actions.
    """

    def __init__(
        self,
        initial_state: StateT,
        action_map: dict[ActionEnumT, Reducer],
    ):
        self._state: StateT = initial_state
        self._action_map: dict[ActionEnumT, Reducer] = action_map
        self._subscribers: list[Callable[[StateT], None]] = []

    def subscribe(self, listener: Callable[[StateT], None]) -> Callable[[], None]:
        """
        Register a listener to be called whenever the state changes.
        Returns an unsubscribe function.
        """
        self._subscribers.append(listener)

        def unsubscribe() -> None:
            self._subscribers.remove(listener)
        return unsubscribe

    def dispatch(self, action: ActionEnumT, payload: Any = None) -> None:
        """
        Dispatch an action by Enum member, plus an optional payload.
        Example usage:
            store.dispatch(action=MyEnum.SOME_ACTION, payload=123)
        """
        if action not in self._action_map:
            raise ValueError(f"Unknown action: {action!r}")

        reducer = self._action_map[action]
        new_state = reducer(self._state.model_copy(), payload)

        # If state changed, notify subscribers
        if new_state != self._state:
            self._state = new_state
            for subscriber in self._subscribers:
                subscriber(self._state)

    def get_state(self) -> StateT:
        """Return the current state."""
        return self._state

    @property
    def actions(self) -> Iterable[ActionEnumT]:  # Corrected type hint
        """Returns an iterable of the actions enum members."""
        return self._action_map.keys()


def _create_store(
    name: str,
    initial_state: StateT,
    reducers: dict[ActionEnumT, Reducer]
) -> tuple[StateT, dict[ActionEnumT, Reducer]]:
    """
    Emulate Redux Toolkit's createSlice in Python, but with typed Enum keys.
    Returns (initial_state, action_map).
    """
    action_map: dict[ActionEnumT, Reducer] = {}

    for action_enum, reducer_fn in reducers.items():
        def make_handler(fn: Reducer, a_enum: ActionEnumT):
            def handler(state: StateT, payload: Any) -> StateT:
                return fn(state, payload)
            handler.__name__ = f"{name}_{a_enum.value}"
            return handler

        action_map[action_enum] = make_handler(reducer_fn, action_enum)

    return (initial_state, action_map)


class StateStore(_BaseStore[StateT, ActionEnumT], metaclass=abc.ABCMeta):
    """
    An abstract state store that requires subclasses to define:
    - `name` (string)
    - `initial_state` (Pydantic model instance)
    - `reducers` (dict[ActionEnumMember, function(state, payload)->new_state])
    Then automatically wires them up via _create_store.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the name of this store (e.g. 'graph_store')."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def initial_state(self) -> StateT:
        """Return the initial Pydantic state."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def reducers(self) -> dict[ActionEnumT, Reducer]:
        """
        Return {ActionEnumMember: function(state, payload) -> newState}.
        """
        raise NotImplementedError

    def __init__(self) -> None:
        init_state, action_map = _create_store(
            self.name,
            self.initial_state,
            self.reducers
        )
        super().__init__(init_state, action_map)
