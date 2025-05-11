from abc import ABC, abstractmethod
from typing import Generic

from jsonpatch import JsonPatch
from loguru import logger
from opentelemetry import trace

from junjo.store import StoreT
from junjo.telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from junjo.util import generate_safe_id


class Node(Generic[StoreT], ABC):
    """
    Nodes are the building blocks of a workflow. They represent a single unit of work
    that can be executed within the context of a workflow.

    Place business logic to be executed by the node in the `service` method.
    The `service` method is where the main logic of the node resides. It will be wrapped and
    annotated with OpenTelemetry tracing.

    The Node is meant to remain decoupled from your business logic. While you can place business logic
    directly in the `service` method, it is recommended that you call a service function located in a
    separate module. This allows for better separation of concerns and makes it easier to test and
    maintain your code.

    Type Parameters:
        StoreT: The workflow store type that will be passed into this node during execution.

    Responsibilities:
        - The Workflow passes the store to the node's execute function.
        - The service function implements side effects using that store.

    Example implementation:
    .. code-block:: python

        class SaveMessageNode(Node[MessageWorkflowStore]):
            async def service(self, store) -> None:
                state = await store.get_state() # Get the current state

                # Perform some business logic
                sentiment = await get_messasge_sentiment(state.message)

                # Perform a state update
                await store.set_message_sentiment(sentiment)
    """

    def __init__(
        self,
    ):
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
        """Returns the list of patches that have been applied to the state by this node."""
        return self._patches

    def add_patch(self, patch: JsonPatch) -> None:
        """Adds a patch to the list of patches."""
        self._patches.append(patch)

    @abstractmethod
    async def service(self, store: StoreT) -> None:
        """
        This is main logic of the node. The concrete implementation of this method
        should contain the side effects that this node will perform.

        This method is called by the `execute` method of the node. The `execute`
        method is responsible for tracing and error handling.

        The `service` method should not be called directly. Instead, it should be
        called by the `execute` method of the node.

        DO NOT EXECUTE `node.service()` DIRECTLY!
        Use `node.execute()` instead.

        Args:
            store (StoreT): The store that will be passed to the node's service function.
        """
        raise NotImplementedError

    async def execute(
            self,
            store: StoreT,
            parent_id: str,
        ) -> None:
        """
        Execute the Node's service function with OpenTelemetry tracing.

        This method is responsible for tracing and error handling. It will
        acquire a tracer, start a new span, and call the `service` method.
        The `service` method should contain the side effects that this node will
        perform.

        Args:
            store (StoreT): The store that will be passed to the node's service function.
            parent_id (str): The ID of the parent span. This is used to create a
                child span for this node's execution.
        """

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            try:
                # Set an attribute on the span
                span.set_attribute("junjo.span_type", JunjoOtelSpanTypes.NODE)
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                # Perform your async operation
                await self.service(store)

            except Exception as e:
                logger.exception("Error executing node service", e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
                raise
