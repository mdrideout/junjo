import abc
import asyncio
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from junjo.node import Node
from junjo.state import BaseState

StateT = TypeVar("StateT", bound=BaseState)
StoreT = TypeVar("StoreT", bound="BaseStore")

# Type alias: each subscriber can be either a sync callable or an async callable (returns an Awaitable).
Subscriber = Callable[[StateT], None] | Callable[[StateT], Awaitable[None]]

class BaseStore(Generic[StateT], metaclass=abc.ABCMeta):
    """
    An abstract base for a "store" that manages a Pydantic state.
    Subclasses must provide an initial_state property.
    """

    def __init__(self, initial_state: StateT) -> None:
        # Use an asyncio.Lock for concurrency control in an async environment
        self._lock = asyncio.Lock()

        # The current state of the store
        self._state: StateT = initial_state

        # Each subscriber can be a synchronous or asynchronous function
        self._subscribers: list[Subscriber] = []

    async def subscribe(self, listener: Subscriber) -> Callable[[], Awaitable[None]]:
        """
        Register a listener (sync or async callable) to be called whenever the state changes.
        Returns an *async* unsubscribe function that, when awaited, removes this listener.
        """

        async with self._lock:
            self._subscribers.append(listener)

        async def unsubscribe() -> None:
            """
            Async function to remove the listener from the subscriber list.
            We lock again to ensure concurrency safety.
            """
            async with self._lock:
                if listener in self._subscribers:
                    self._subscribers.remove(listener)

        return unsubscribe

    async def get_state(self) -> StateT:
        """
        Return a shallow copy of the current state.
        (Follows immutability principle)
        """
        async with self._lock:
            # Return a separate copy of the Pydantic model so outside code doesn't mutate the store
            return self._state.model_copy()


    async def get_state_json(self) -> str:
        """
        Return the current state as a JSON string.
        """
        async with self._lock:
            return self._state.model_dump_json()

    async def set_state(self, node: Node, update: dict,) -> None:
        """
        Public API to partially update the store state with a dict of changes.
        - Immutable update with a deep state copy
        - Merges the current state with `updates` using `model_copy(update=...)`.
        - Validates that each updated field is valid for StateT.
        - If there's a change, notifies subscribers outside the lock.
        """
        subscribers_to_notify: list[Subscriber] = []
        async with self._lock:
            # Create a new instance with partial updates, deep=True for true immutability
            new_state = self._state.model_copy(update=update, deep=True)

            # Only notify if something actually changed
            if new_state != self._state:
                self._state = new_state
                subscribers_to_notify = list(self._subscribers)

        # Notify subscribers outside the lock
        if subscribers_to_notify:
            await self._notify_subscribers(new_state, subscribers_to_notify)

    async def _notify_subscribers(self, new_state: StateT, subscribers: list[Subscriber]) -> None:
        """
        Private helper to call subscribers once the lock is released.
        """
        for subscriber in subscribers:
            result = subscriber(new_state)
            # If the subscriber is async, it returns a coroutine or awaitable
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                await result

