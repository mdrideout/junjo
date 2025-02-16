import abc
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

StateT = TypeVar("StateT", bound=BaseModel)
StoreT = TypeVar("StoreT", bound="BaseStore")

class BaseStore(Generic[StateT], metaclass=abc.ABCMeta):
    """
    An abstract base for a "store" that manages a Pydantic state.
    Subclasses must provide an initial_state property.
    """

    def __init__(self, initial_state: StateT) -> None:
        # Use the subclass's initial_state property to set up the store
        self._state: StateT = initial_state
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

    def get_state(self) -> StateT:
        """
        Return the current state.
        """
        return self._state

    def _update_state_and_notify(self, new_state: StateT) -> None:
        """
        Update state and notify.

        If state has changed:
        - Updates state
        - Notifies subscribers
        """
        if new_state != self._state:
            self._state = new_state
            for subscriber in self._subscribers:
                subscriber(self._state)


def state_action(func: Callable[..., StateT]) -> Callable[..., StateT]:
    """
    A decorator for store state update functions.

    Ensures that:
    1. The decorated method returns a new state object of the correct type.
    2. `_update_state_and_notify` is called to update the store and notify subscribers.
    """

    def wrapper(self: BaseStore[StateT], *args: Any, **kwargs: Any) -> StateT:
        new_state = func(self, *args, **kwargs)
        if not isinstance(new_state, self._state.__class__):  # Check against current state's type
            raise TypeError(f"Action method must return a {self._state.__class__.__name__} object.")
        self._update_state_and_notify(new_state)
        return new_state

    return wrapper
