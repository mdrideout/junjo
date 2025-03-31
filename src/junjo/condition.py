from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from junjo.state import BaseState

StateT = TypeVar("StateT", bound=BaseState)

class Condition(Generic[StateT], ABC):
    """
    Abstract base class for edge conditions in a workflow graph.

    A condition determines whether a transition along an edge should occur
    based only on the current state.
    """

    @abstractmethod
    def evaluate(self, state: StateT) -> bool:
        """
        Evaluates whether the transition should occur based on store state.

        Args:
            store: The workflow store containing the current state.

        Returns:
            True if the transition should occur, False otherwise.
        """
        pass

    def __str__(self) -> str:
        """
        Default string representation of the condition.
        Subclasses can override this for more specific representations.
        """
        return self.__class__.__name__
