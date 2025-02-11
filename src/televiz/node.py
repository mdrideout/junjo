from abc import ABC, abstractmethod
from typing import Any

from nanoid import generate


class Node(ABC):
    """
    Base class for all nodes in the televiz graph.

    This class provides the basic structure and interface for nodes,
    including input/output handling, execution, and validation.
    """

    def __init__(self, **kwargs):
        """
        Initializes the Node.

        Args:
            **kwargs: Keyword arguments representing node inputs.  These
                      will be set as attributes on the node instance.
        """
        super().__init__()  # Good practice, even if not strictly necessary now
        self._id = generate()
        self._name: str
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}

        # Set inputs as attributes and store in _inputs
        for key, value in kwargs.items():
            setattr(self, key, value)
            self._inputs[key] = value

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id


    @property
    def inputs(self) -> dict[str, Any]:
        """Returns a dictionary of input values."""
        return self._inputs

    @property
    def outputs(self) -> dict[str, Any]:
        """Returns a dictionary of output values."""
        return self._outputs

    @abstractmethod
    async def execute(self) -> None:
        """
        Executes the node.

        This method should perform the primary logic of the node,
        setting output values as necessary.
        """
        raise NotImplementedError
