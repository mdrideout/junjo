from abc import ABC, abstractmethod
from typing import Generic, get_type_hints

from nanoid import generate
from pydantic import BaseModel

from junjo.store.store import BaseStore, StateT, StoreT
from junjo.workflow_context import WorkflowContextManager


class Node(Generic[StateT, StoreT], ABC):
    """
    Base class for all nodes in the junjo graph.

    The Node acts as a type contract for inputs and outputs at this stage of the workflow.
    - The Node defines types for input and output
    - The logic function is expected to accept this input, and produce the output
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
    async def service(self, state: StateT, store: StoreT) -> StateT:
        """The main logic of the node."""
        raise NotImplementedError

    async def _execute(self, workflow_id: str) -> None:
        """
        Validate the node and execute its service function.
        """

        # Validate the service function has the appropriate signature
        if not callable(self.service):
            raise ValueError("Service function must be callable")

        # Validate service function params: store
        type_hints = get_type_hints(self.service)
        if "store" not in type_hints:
            raise ValueError(f"Service function must have a 'store' parameter of type {StoreT}")
        if not issubclass(type_hints["store"], BaseStore):
            raise ValueError(f"Service function must have a 'store' parameter of type {StoreT}")


        # Validate service function params: state
        if "state" not in type_hints:
            raise ValueError(f"Service function must have a 'state' parameter of type {StateT}")
        if not issubclass(type_hints["state"], BaseModel):
            raise ValueError(f"Service function must have a 'state' parameter of type {StateT}")

        # Validate the return type of the service function
        if "return" not in type_hints:
            raise ValueError(f"Service function must have a return type of {StateT}")
        if not issubclass(type_hints["return"], BaseModel):
            raise ValueError(f"Service function must have a return type of {StateT}")


        # Get and validate the store from context
        store = WorkflowContextManager.get_store(workflow_id)
        if store is None:
            raise ValueError("Store is not available")

        # Get and validate the state from the store
        state = store.get_state()
        if state is None:
            raise ValueError("State is not available")

        # Execute the service
        try:
            await self.service(state, store)
        except Exception as e:
            print(f"Error executing service: {e}")
            return



