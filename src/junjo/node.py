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
    Base class for all nodes in the junjo graph.

    Type Parameters:
        StoreT: The workflow store type that will be passed into this node during execution.

    Responsibilities:
        - The Workflow passes the store to the node’s execute function.
        - The service function implements side effects using that store.
    """

    def __init__(
        self,
    ):
        """Initialize the node"""
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
        This is main logic of the node.

        DO NOT EXECUTE `node.service()` DIRECTLY!
        Use `node.execute()` instead.

        Args
            :param store: The store will be passed to this node during execution
        """
        raise NotImplementedError

    async def execute(
            self,
            store: StoreT,
            parent_id: str,
        ) -> None:
        """
        Execute the Node's service function with OpenTelemetry tracing.
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
