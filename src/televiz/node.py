from abc import ABC, abstractmethod
from typing import Any


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
            *args: Positional arguments (generally discouraged for nodes,
                   favor keyword arguments).
            **kwargs: Keyword arguments representing node inputs.  These
                      will be set as attributes on the node instance.
        """
        super().__init__()  # Good practice, even if not strictly necessary now
        self._inputs: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}

        # Set inputs as attributes and store in _inputs
        for key, value in kwargs.items():
            setattr(self, key, value)
            self._inputs[key] = value

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
