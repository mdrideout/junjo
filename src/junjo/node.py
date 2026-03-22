import asyncio
from abc import ABC, abstractmethod
from typing import Generic

from jsonpatch import JsonPatch
from opentelemetry import trace

from .store import StoreT
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME
from .telemetry.span_lifecycle import get_span_identifiers, mark_span_cancelled
from .util import generate_safe_id


class Node(Generic[StoreT], ABC):
    """
    Nodes are the building blocks of a workflow. They represent a single unit of
    work that can be executed within the context of a workflow.

    Place business logic to be executed by the node in :meth:`service`. Junjo
    wraps that service method with OpenTelemetry tracing, error handling, and
    lifecycle hook dispatch during :meth:`execute`.

    The ``Node`` type is meant to remain decoupled from your application's
    domain logic. While you can place business logic directly in the
    :meth:`service` method, it is recommended that you call a service function
    located in a separate module. This keeps nodes easy to test, easier to
    understand, and focused on orchestration rather than implementation detail.

    ``StoreT`` is the workflow store type that will be passed into this node
    during execution.

    Nodes have three main responsibilities:

    - The workflow passes the run-local store to the node's
      :meth:`execute` method.
    - :meth:`execute` manages tracing, lifecycle hooks, and error handling.
    - :meth:`service` performs the side effects for this unit of work.

    .. rubric:: Example implementation

    .. code-block:: python

        class SaveMessageNode(Node[MessageWorkflowStore]):
            async def service(self, store) -> None:
                state = await store.get_state()
                sentiment = await get_message_sentiment(state.message)
                await store.set_message_sentiment(sentiment)
    """

    def __init__(self):
        super().__init__()
        self._id = generate_safe_id()
        self._patches: list[JsonPatch] = []

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @property
    def name(self) -> str:
        """Returns the name of the node class instance."""
        return self.__class__.__name__

    @property
    def patches(self) -> list[JsonPatch]:
        """Returns the list of state patches that have been applied by this node."""
        return self._patches

    def add_patch(self, patch: JsonPatch) -> None:
        """Adds a patch to the list of patches."""
        self._patches.append(patch)

    @abstractmethod
    async def service(self, store: StoreT) -> None:
        """
        This is the main logic of the node.

        The concrete implementation of this method should contain the side
        effects that this node will perform. The method is called by
        :meth:`execute`, which is responsible for tracing, lifecycle dispatch,
        and error handling.

        The :meth:`service` method should not be called directly. Instead, it
        should be called by the :meth:`execute` method of the node.

        DO NOT EXECUTE ``node.service()`` DIRECTLY!
        Use ``node.execute()`` instead.

        :param store: The run-local store passed to the node's service
            function.
        :type store: StoreT
        """
        raise NotImplementedError

    async def execute(self, store: StoreT, parent_id: str) -> None:
        """
        Execute the node's :meth:`service` method with tracing and lifecycle
        dispatch.

        This method acquires a tracer, opens a node span, emits lifecycle
        events, and then calls :meth:`service`. Completed, failed, and cancelled
        lifecycle hooks are dispatched only after the span has been finalized
        and closed.

        :param store: The run-local store for the current workflow execution.
        :type store: StoreT
        :param parent_id: The identifier of the parent workflow or subflow.
            This becomes the parent id recorded on the node span.
        :type parent_id: str
        """
        lifecycle_context = store._lifecycle_context
        prepared_terminal_event = None
        failure: Exception | None = None
        cancellation: asyncio.CancelledError | None = None

        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        with tracer.start_as_current_span(self.name) as span:
            try:
                span.set_attribute("junjo.span_type", "node")
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    await lifecycle_context.dispatcher.node_started(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

                await self.service(store)

                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.node_completed(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                cancellation = exc
                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.node_cancelled(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        reason=str(exc.args[0]) if exc.args else "cancelled",
                        trace_id=trace_id,
                        span_id=span_id,
                    )

            except Exception as exc:
                print("Error executing node service", exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                failure = exc
                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.node_failed(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        error=exc,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

        if lifecycle_context is not None:
            await lifecycle_context.dispatcher.dispatch(prepared_terminal_event)

        if cancellation is not None:
            raise cancellation
        if failure is not None:
            raise failure
