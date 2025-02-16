from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from nanoid import generate
from pydantic import BaseModel

# Define type variables constrained to BaseModel
InputModelType = TypeVar("InputModelType", bound=BaseModel)
OutputModelType = TypeVar("OutputModelType", bound=BaseModel)

class Node(Generic[InputModelType, OutputModelType], ABC):
    """
    Base class for all nodes in the junjo graph.

    Nodes define the *interface* or *contract* for data processing steps,
    and accepts a logic function that reads and returns data according to
    the contract.
    """

    def __init__(self, logic: Callable[[InputModelType], Awaitable[OutputModelType]]):
        """
        Initializes the Node.
        """
        super().__init__()
        self._id = generate()
        self._logic = logic

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    async def execute(self) -> OutputModelType:
        """
        Executes the node's logic.

        This method should perform the primary logic of the node,
        setting output values as necessary.
        """

        # TODO: Must read the input data from somewhere
        data = None
        if data is None:
            raise ValueError("Not reading input data yet.")

        return await self._logic(data)



