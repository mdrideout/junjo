import abc
import asyncio
import inspect
from types import NoneType
from typing import Generic, TypeVar

import jsonpatch
from opentelemetry import trace
from pydantic import ValidationError

from .state import BaseState
from .util import generate_safe_id

# State / Store
StateT = TypeVar("StateT", bound=BaseState)
StoreT = TypeVar("StoreT", bound="BaseStore")

# Parent State / Store
ParentStateT = TypeVar("ParentStateT", bound="BaseState | NoneType")
ParentStoreT = TypeVar("ParentStoreT", bound="BaseStore | NoneType")

class BaseStore(Generic[StateT], metaclass=abc.ABCMeta):
    """
    BaseStore represents a generic store for managing the state of a workflow.
    It is designed to be subclassed with a specific state type (Pydantic model).

    The store is responsible for:
        | - Managing the state of the workflow.
        | - Making immuable updates to the state safely in a concurrent environment.
        | - Validating state updates against the Pydantic model.

    The store uses an asyncio.Lock to ensure that state updates are thread-safe.
    This is important in an async environment where multiple coroutines may be
    trying to update the state at the same time.
    """

    def __init__(self, initial_state: StateT) -> None:
        """
        Args:
            initial_state: The initial state of the store, based on the Pydantic model.
        """
        # Use an asyncio.Lock for concurrency control in an async environment
        self._lock = asyncio.Lock()

        # Generate a unique ID for the store instance
        self._id = generate_safe_id()

        # The current state of the store
        self._state: StateT = initial_state

    @property
    def id(self) -> str:
        """Returns the unique identifier of a given store's implementation."""
        return self._id

    async def get_state(self) -> StateT:
        """
        Return a detached deep copy of the current state.
        Mutating the returned snapshot must not mutate the store.
        """
        async with self._lock:
            return self._state.model_copy(deep=True)


    async def get_state_json(self) -> str:
        """
        Return the current state as a JSON string.
        """
        async with self._lock:
            return self._state.model_dump_json()

    async def set_state(self, update: dict) -> None:
        """
        Update the store's state with a dictionary of changes.
        | - Immutable update with a deep state copy
        | - Merges the current state with `updates` using `model_copy(update=...)`.
        | - Validates that each updated field is valid for StateT.

        Args:
            update: A dictionary of updates to apply to the state.

        .. code-block:: python

            class MessageWorkflowState(BaseState): # A pydantic model to represent the state
                received_message: Message

            class MessageWorkflowStore(BaseStore[MessageWorkflowState]): # A concrete store for MessageWorkflowState
                async def set_received_message(self, payload: Message) -> None:
                    await self.set_state({"received_message": payload})

            payload = Message(...)
            await store.set_received_message(payload) # Utilizes the set_state method to update a particular field
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

        async with self._lock:
            try:
                new_state = self._state.__class__.model_validate(
                    {**self._state.model_dump(), **update}
                )
            except ValidationError as e:
                raise ValueError(
                    f"Invalid state update from caller {caller_class_name} -> {caller_function_name}.\n"
                    f"Check that you are updating a valid state property and type: {e}"
                ) from e

            # Patch starts as None
            patch = None

            # Only notify if something actually changed
            if new_state != self._state:
                state_json_before = self._state.model_dump(mode="json")
                state_json_after = new_state.model_dump(mode="json")

                # Calculate the patch
                patch = jsonpatch.make_patch(state_json_before, state_json_after)
                # print("PATCH: ", patch)

                # Update the stack (have lock)
                self._state = new_state

            # --- OpenTelemetry Event (call even if nothing changed) --- #
            current_span = trace.get_current_span()
            if current_span.is_recording():
                current_span.add_event(
                    name="set_state",
                    attributes={
                        "id": generate_safe_id(),
                        "junjo.store.name": caller_class_name,
                        "junjo.store.id": self.id,
                        "junjo.store.action": caller_function_name,
                        "junjo.state_json_patch": patch.to_string() if patch else "{}", # Empty if nothing changed
                    },
                )
            # --- End OpenTelemetry Event --- #
