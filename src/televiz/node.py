from abc import ABC, abstractmethod


class Node(ABC):
    """
    Base class for all nodes in the televiz graph.

    This class provides the basic structure and interface for nodes,
    including input/output handling, execution, and validation.
    """

    @abstractmethod
    def execute(self):
        pass
