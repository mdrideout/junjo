from abc import ABC, abstractmethod
from typing import Generic, get_type_hints

from nanoid import generate

from junjo.store import BaseStore, StoreT
from junjo.workflow_context import WorkflowContextManager


class Node(Generic[StoreT], ABC):
    """
    Base class for all nodes in the junjo graph.

    The Workflow passes the store to the node's service function.
    - The Node's 
    - The action function is expected to carry out side effects on the output
    """

    def __init__(
        self,
    ):
        """Initialize the node"""
        super().__init__()
        self._id = generate()

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @abstractmethod
    async def service(self, store: StoreT) -> None:
        """The main logic of the node.

        Args
            :param store: The store will be passed to this node during execution
        """
        raise NotImplementedError

    async def _execute(self, workflow_id: str) -> None:
        """
        Validate the node and execute its service function.
        """

        # Validate the service function
        self._validate_service_function()

        # Get and validate the store from context
        store = WorkflowContextManager.get_store(workflow_id)
        if store is None:
            raise ValueError("Store is not available")

        # Execute the service
        try:
            await self.service(store) # (cannot know store is StoreT here? it works...)
        except Exception as e:
            print(f"Error executing service: {e}")
            return


    def _validate_service_function(self) -> None:
        """Validate the service function of the node."""

        # Validate the service function has the appropriate signature
        if not callable(self.service):
            raise ValueError("Service function must be callable")

        # Validate service function params: store
        type_hints = get_type_hints(self.service)
        if "store" not in type_hints:
            raise ValueError(f"Service function must have a 'store' parameter of type {StoreT}")
        if not issubclass(type_hints["store"], BaseStore):
            raise ValueError(f"Service function must have a 'store' parameter of type {StoreT}")

