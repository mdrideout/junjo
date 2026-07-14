import abc
import asyncio
import inspect
from types import NoneType
from typing import Generic, TypeVar

from opentelemetry import trace
from pydantic import ValidationError

from ._identity import (
    get_active_executable_identity,
    get_parent_active_executable_identity,
)
from ._json import JsonNestingDepthError, normalize_json, validate_json_nesting
from ._lifecycle import GraphStoreLifecycleContext
from .state import BaseState
from .telemetry.span_lifecycle import get_current_span_identifiers
from .telemetry.store_evidence import StoreEvidenceTracker, StoreOwnerEvidence
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

    - Managing the state of a workflow or subflow execution.
    - Making immutable updates to that state safely in a concurrent
      environment.
    - Validating committed updates against the underlying Pydantic model.

    The store uses an :class:`asyncio.Lock` to ensure that state updates are
    concurrency-safe. Each committed update is derived, validated, and applied
    against the exact locked state version it modifies, which prevents stale
    validate-then-apply races under concurrent execution.

    Subclass ``BaseStore`` with your own state type and expose domain-specific
    actions that call :meth:`set_state`.

    .. rubric:: Example

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
        :param initial_state: The initial state of the store.
        :type initial_state: StateT
        """
        raw_initial_state = {
            field_name: getattr(initial_state, field_name) for field_name in type(initial_state).model_fields
        }
        validate_json_nesting(raw_initial_state)
        try:
            owned_initial_state = initial_state.model_copy(deep=True)
            initial_projection = normalize_json(owned_initial_state.model_dump(mode="json"))
        except RecursionError as exc:
            raise JsonNestingDepthError("Store state serialization exceeded the JSON nesting bound.") from exc
        self._lock = asyncio.Lock()
        self._id = generate_safe_id()
        self._state: StateT = owned_initial_state
        self._lifecycle_context: GraphStoreLifecycleContext | None = None
        self._telemetry_evidence = StoreEvidenceTracker(initial_projection)

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

    def _set_lifecycle_context(self, context: GraphStoreLifecycleContext | None) -> None:
        """Attach internal lifecycle dispatch context for this execution."""
        self._lifecycle_context = context

    def _current_runtime_state_data(self) -> dict[str, object]:
        """
        Return current state field values for runtime state transitions.

        This intentionally avoids ``model_dump()`` because Pydantic
        serialization controls such as ``Field(exclude=True)`` and
        ``field_serializer`` are telemetry-facing concerns, not live state
        transition mechanics.
        """
        state_snapshot = self._state.model_copy(deep=True)
        return {field_name: getattr(state_snapshot, field_name) for field_name in type(state_snapshot).model_fields}

    async def _get_store_owner_evidence(self) -> StoreOwnerEvidence:
        """Return verified terminal evidence under the Store lock."""

        async with self._lock:
            return self._telemetry_evidence.finalize(normalize_json(self._state.model_dump(mode="json")))

    def _get_initial_store_owner_evidence(self) -> StoreOwnerEvidence:
        """Return initial evidence before a newly created Store is published."""

        return self._telemetry_evidence.finalize(normalize_json(self._state.model_dump(mode="json")))

    async def _get_store_revision(self) -> int:
        """Return the current live-state revision for semantic operation evidence."""

        async with self._lock:
            return self._telemetry_evidence.revision

    async def set_state(self, update: dict) -> None:
        """
        Update the store's state with a dictionary of changes.

        The update is shallow-merged with the current locked state at the
        top-level field boundary, validated against the store's Pydantic model,
        and committed atomically if it changes the state. Nested mappings or
        nested models are replaced as field values; Junjo does not recursively
        deep-merge nested structures. This method also emits OpenTelemetry
        ``set_state`` events and lifecycle state-changed hooks when a commit
        occurs.

        :param update: A dictionary of updates to apply to the state.
        :type update: dict

        .. code-block:: python

            class MessageWorkflowState(BaseState):
                received_message: Message

            class MessageWorkflowStore(BaseStore[MessageWorkflowState]):
                async def set_received_message(self, payload: Message) -> None:
                    await self.set_state({"received_message": payload})

            payload = Message(...)
            await store.set_received_message(payload)

        .. note::

            Validation happens while the store lock is held, so every committed
            update is validated against the exact state version it will be
            applied to.

        .. note::

            Updates are top-level field patches. To update part of a nested
            structure, build the replacement nested value in your store action
            and pass that complete value to ``set_state``.

        .. note::

            State transitions use runtime field values, not serialized state
            dumps. Pydantic serialization controls such as
            ``Field(exclude=True)`` and ``field_serializer`` affect telemetry
            payloads but do not remove or rewrite live runtime state.

        .. note::

            If the resulting state is unchanged, the store remains untouched
            and an empty patch is recorded in telemetry.
        """
        caller_frame = inspect.currentframe()
        if caller_frame:
            caller_frame = caller_frame.f_back
        caller_function_name = caller_frame.f_code.co_name if caller_frame else "unknown action"
        store_name = type(self).__name__

        state_changed_payload: dict | None = None
        async with self._lock:
            validate_json_nesting(update)
            try:
                new_state = type(self._state).model_validate({**self._current_runtime_state_data(), **update})
            except ValidationError as e:
                raise ValueError(
                    f"Invalid state update from caller {store_name} -> {caller_function_name}.\n"
                    f"Check that you are updating a valid state property and type: {e}"
                ) from e

            state_json_before = normalize_json(self._state.model_dump(mode="json"))
            state_json_after = normalize_json(new_state.model_dump(mode="json"))
            live_state_changed = new_state != self._state
            transition = self._telemetry_evidence.record(
                projection_before=state_json_before,
                projection_after=state_json_after,
                live_state_changed=live_state_changed,
            )

            if live_state_changed:
                self._state = new_state

            current_span = trace.get_current_span()
            if current_span.is_recording():
                current_span.add_event(
                    name="set_state",
                    attributes={
                        "id": generate_safe_id(),
                        "junjo.store.name": store_name,
                        "junjo.store.id": self.id,
                        "junjo.store.action": caller_function_name,
                        **self._telemetry_evidence.transition_attributes(transition),
                    },
                )

            if live_state_changed and self._lifecycle_context is not None:
                trace_id, span_id = get_current_span_identifiers()
                active_identity = get_active_executable_identity()
                parent_active_identity = get_parent_active_executable_identity()
                state_changed_payload = {
                    "run_id": self._lifecycle_context.run_id,
                    "executable_definition_id": (
                        active_identity.executable_definition_id
                        if active_identity is not None
                        else self._lifecycle_context.executable_definition_id
                    ),
                    "name": (
                        active_identity.executable_name if active_identity is not None else self._lifecycle_context.name
                    ),
                    "span_type": (
                        active_identity.executable_type
                        if active_identity is not None
                        else self._lifecycle_context.executable_type
                    ),
                    "store_id": self.id,
                    "store_name": store_name,
                    "action_name": caller_function_name,
                    "patch": transition.patch_json,
                    "state": new_state.model_copy(deep=True),
                    "parent_executable_definition_id": (
                        parent_active_identity.executable_definition_id
                        if parent_active_identity is not None
                        else self._lifecycle_context.executable_definition_id
                    ),
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "executable_runtime_id": (
                        active_identity.executable_runtime_id
                        if active_identity is not None
                        else self._lifecycle_context.executable_runtime_id
                    ),
                    "executable_structural_id": (
                        active_identity.executable_structural_id
                        if active_identity is not None
                        else self._lifecycle_context.executable_structural_id
                    ),
                    "enclosing_graph_structural_id": (self._lifecycle_context.enclosing_graph_structural_id),
                    "parent_executable_runtime_id": (
                        parent_active_identity.executable_runtime_id if parent_active_identity is not None else None
                    ),
                    "parent_executable_structural_id": (
                        parent_active_identity.executable_structural_id if parent_active_identity is not None else None
                    ),
                    "parent_executable_type": (
                        parent_active_identity.executable_type if parent_active_identity is not None else None
                    ),
                }

        if state_changed_payload is not None and self._lifecycle_context is not None:
            await self._lifecycle_context.dispatcher.state_changed(**state_changed_payload)

    async def _validate_state_update(self, update: dict) -> None:
        """Validate one prospective state and exact patch without committing it.

        Execution kernels use this protected boundary when an application
        value must be classified before entering a later terminal transaction.
        Public Store mutations still flow only through :meth:`set_state`.
        """

        async with self._lock:
            validate_json_nesting(update)
            try:
                new_state = type(self._state).model_validate({**self._current_runtime_state_data(), **update})
            except ValidationError as exc:
                raise ValueError("Invalid prospective state update.") from exc
            state_json_before = normalize_json(self._state.model_dump(mode="json"))
            state_json_after = normalize_json(new_state.model_dump(mode="json"))
            self._telemetry_evidence.validate_transition(
                projection_before=state_json_before,
                projection_after=state_json_after,
            )
