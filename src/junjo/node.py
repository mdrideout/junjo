from abc import ABC, abstractmethod
from typing import Generic

from nanoid import generate

from junjo.store.store import StateT, StoreT
from junjo.workflow_context import WorkflowContextManager

# ServiceFn = Callable[[StateT], StateT]

class BaseNode(Generic[StateT, StoreT], ABC):
    """
    Base class for all nodes in the junjo graph.

    The Node acts as a type contract for inputs and outputs at this stage of the workflow.
    - The Node defines types for input and output
    - The logic function is expected to accept this input, and produce the output
    - The action function is expected to carry out side effects on the output
    """

    def __init__(
        self,
        # service: ServiceFn
    ):
        """Initialize the node"""
        super().__init__()
        self._id = generate()
        # self.service = service

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @abstractmethod
    async def service(self, store: StoreT) -> StateT:
        """The main logic of the node."""
        raise NotImplementedError

    async def _execute(self, workflow_id: str) -> None:
        """
        Validate the node and execute its service function.
        """

        # Validate the service function has the appropriate signature
        if not callable(self.service):
            raise ValueError("Service function must be callable")

        # Validate the store parameter for StoreT
        if not hasattr(self.service, "__annotations__") or "store" not in self.service.__annotations__:
            raise ValueError(f"Service function must have a 'store' parameter of type {StoreT}")

        # Get the current store
        store = WorkflowContextManager.get_store(workflow_id)
        if store is None:
            raise ValueError("Store is not available")

        # Execute the service
        try:
            result = await self.service(store)
        except Exception as e:
            print(f"Error executing service: {e}")
            return

    # async def execute(self) -> None:
    #     """
    #     Executes the node's logic.

    #     This method should perform the primary logic of the node,
    #     setting output values as necessary.
    #     """

    #     # Validate the service function has the appropriate signature
    #     if not callable(self.service):
    #         raise ValueError("Service function must be callable")

    #     # Validate has a state parameter for StateT
    #     if not hasattr(self.service, "__annotations__") or "state" not in self.service.__annotations__:
    #         raise ValueError(f"Service function must have a 'state' parameter of type {StateT}")

    #     # Get the current state
    #     state = self.get_state()

    #     # Execute the service
    #     try:
    #         result = await self.service(state)
    #     except Exception as e:
    #         print(f"Error executing service: {e}")
    #         return

    #     # Validate the result
    #     try:
    #         validated_result = self.state.model_validate(result)
    #     except ValidationError as e:
    #         print(f"Service result does not match state model: {e}")
    #         return

    #     # Update the state
    #     self.state = self.state.model_copy(update=validated_result.model_dump())





