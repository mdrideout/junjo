import abc
import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

import jsonpatch
from nanoid import generate
from opentelemetry import trace
from pydantic import ValidationError

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

    async def set_state(self, node: Node, update: dict) -> None:
        """
        Public API to partially update the store state with a dict of changes.
        - Immutable update with a deep state copy
        - Merges the current state with `updates` using `model_copy(update=...)`.
        - Validates that each updated field is valid for StateT.
        - If there's a change, notifies subscribers outside the lock.
        """
        # Get the caller function's name and class name for telemetry purposes
        caller_frame = inspect.currentframe()
        if caller_frame:
            caller_frame = caller_frame.f_back
        caller_function_name = caller_frame.f_code.co_name if caller_frame else "unknown action"

        # Get the caller class name if available
        caller_class_name = "unknown store"
        if caller_frame and "self" in caller_frame.f_locals:
            caller_class_name = caller_frame.f_locals["self"].__class__.__name__

        # Validate the update dictionary against the state's model OUTSIDE the lock
        try:
            self._state.__class__.model_validate(
                {**self._state.model_dump(), **update}
            )
        except ValidationError as e:
            raise ValueError(
                f"Invalid state update in node {node.name}. \
                  Check that you are updating a valid state property and type: {e}"
            ) from e

        subscribers_to_notify: list[Subscriber] = []
        async with self._lock:
            # Create a new instance with partial updates, deep=True for true immutability
            new_state = self._state.model_copy(update=update, deep=True)

            # Only notify if something actually changed
            if new_state != self._state:
                state_json_before = self._state.model_dump(mode="json")
                state_json_after = new_state.model_dump(mode="json")

                # Calculate the patch
                patch = jsonpatch.make_patch(state_json_before, state_json_after)
                print("PATCH: ", patch)

                # Update the stack (have lock)
                self._state = new_state
                subscribers_to_notify = list(self._subscribers)

                # --- OpenTelemetry Event --- #
                current_span = trace.get_current_span()
                if current_span.is_recording():
                    current_span.add_event(
                        name="set_state",
                        attributes={
                            "id": generate(),
                            "junjo.node.id": node.id,
                            "junjo.store.name": caller_class_name,
                            "junjo.store.action": caller_function_name,
                            "junjo.state_json_patch": patch.to_string(),
                        },
                    )
                # --- End OpenTelemetry Event --- #

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

