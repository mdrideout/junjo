import abc
import asyncio
import inspect
from types import NoneType
from typing import Generic, TypeVar

import jsonpatch
from opentelemetry import trace
from pydantic import ValidationError

from ._lifecycle import StoreLifecycleContext
from .state import BaseState
from .telemetry.span_lifecycle import get_current_span_identifiers
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
    It is designed to be subclassed with a specific state type (a Pydantic
    model derived from :class:`~junjo.state.BaseState`).

    The store is responsible for:
        | - Managing the state of a workflow or subflow execution.
        | - Making immutable updates to that state safely in a concurrent
            environment.
        | - Validating committed updates against the underlying Pydantic model.

    The store uses an :class:`asyncio.Lock` to ensure that state updates are
    concurrency-safe. Each committed update is derived, validated, and applied
    against the exact locked state version it modifies, which prevents stale
    validate-then-apply races under concurrent execution.

    Subclass ``BaseStore`` with your own state type and expose domain-specific
    actions that call :meth:`set_state`.

    Example:

    .. code-block:: python

        class MyWorkflowState(BaseState):
            user_input: str
            processed_data: dict | None = None

        class MyWorkflowStore(BaseStore[MyWorkflowState]):
            async def set_processed_data(self, data: dict) -> None:
                await self.set_state({"processed_data": data})
    """

    def __init__(self, initial_state: StateT) -> None:
        """
        Args:
            initial_state: The initial state of the store.
        """
        self._lock = asyncio.Lock()
        self._id = generate_safe_id()
        self._state: StateT = initial_state
        self._lifecycle_context: StoreLifecycleContext | None = None

    @property
    def id(self) -> str:
        """Returns the unique identifier of this store instance."""
        return self._id

    async def get_state(self) -> StateT:
        """
        Return a detached deep copy of the current state.

        This method follows the immutability principle for read access: callers
        receive a deep snapshot that can be inspected freely without mutating
        the live store. Store updates must still flow through store actions and
        :meth:`set_state`.
        """
        async with self._lock:
            return self._state.model_copy(deep=True)

    async def get_state_json(self) -> str:
        """
        Return the current state as a JSON string.

        This is useful for logging, tracing, or serializing the current state
        without manually calling ``model_dump_json`` on a snapshot.
        """
        async with self._lock:
            return self._state.model_dump_json()

    def _set_lifecycle_context(self, context: StoreLifecycleContext | None) -> None:
        """Attach internal lifecycle dispatch context for this execution."""
        self._lifecycle_context = context

    async def set_state(self, update: dict) -> None:
        """
        Update the store's state with a dictionary of changes.

        The update is merged with the current locked state, validated against
        the store's Pydantic model, and committed atomically if it changes the
        state. This method also emits OpenTelemetry ``set_state`` events and
        lifecycle state-changed hooks when a commit occurs.

        Args:
            update: A dictionary of updates to apply to the state.

        .. code-block:: python

            class MessageWorkflowState(BaseState):
                received_message: Message

            class MessageWorkflowStore(BaseStore[MessageWorkflowState]):
                async def set_received_message(self, payload: Message) -> None:
                    await self.set_state({"received_message": payload})

            payload = Message(...)
            await store.set_received_message(payload)

        Notes:
            - Validation happens while the store lock is held, so every
              committed update is validated against the exact state version it
              will be applied to.
            - If the resulting state is unchanged, the store remains untouched
              and an empty patch is recorded in telemetry.
        """
        caller_frame = inspect.currentframe()
        if caller_frame:
            caller_frame = caller_frame.f_back
        caller_function_name = caller_frame.f_code.co_name if caller_frame else "unknown action"

        caller_class_name = "unknown store"
        if caller_frame and "self" in caller_frame.f_locals:
            caller_class_name = caller_frame.f_locals["self"].__class__.__name__

        state_changed_payload: dict | None = None
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

            patch = None

            if new_state != self._state:
                state_json_before = self._state.model_dump(mode="json")
                state_json_after = new_state.model_dump(mode="json")
                patch = jsonpatch.make_patch(state_json_before, state_json_after)
                self._state = new_state

            current_span = trace.get_current_span()
            if current_span.is_recording():
                current_span.add_event(
                    name="set_state",
                    attributes={
                        "id": generate_safe_id(),
                        "junjo.store.name": caller_class_name,
                        "junjo.store.id": self.id,
                        "junjo.store.action": caller_function_name,
                        "junjo.state_json_patch": patch.to_string() if patch else "{}",
                    },
                )

            if patch is not None and self._lifecycle_context is not None:
                trace_id, span_id = get_current_span_identifiers()
                state_changed_payload = {
                    "run_id": self._lifecycle_context.run_id,
                    "definition_id": self._lifecycle_context.definition_id,
                    "name": self._lifecycle_context.name,
                    "span_type": self._lifecycle_context.span_type,
                    "store_id": self.id,
                    "store_name": caller_class_name,
                    "action_name": caller_function_name,
                    "patch": patch.to_string(),
                    "state": new_state.model_copy(deep=True),
                    "parent_definition_id": self._lifecycle_context.definition_id,
                    "trace_id": trace_id,
                    "span_id": span_id,
                }

        if state_changed_payload is not None and self._lifecycle_context is not None:
            await self._lifecycle_context.dispatcher.state_changed(**state_changed_payload)
