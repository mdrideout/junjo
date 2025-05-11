from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .state import BaseState

StateT = TypeVar("StateT", bound=BaseState)

class Condition(Generic[StateT], ABC):
    """
    Abstract base class for edge conditions in a workflow graph.

    Implement a concrete condition that determines whether a transition along an edge should occur
    based only on the current state.

    This is designed to be used with the `Edge` class, which represents a directed
    edge in the workflow graph. The condition is evaluated when determining
    whether to transition from the tail node to the head node.

    Type Parameters:
        StateT: The type of the state that the condition will evaluate against.
                This should be a subclass of `BaseState`.

    Responsibilities:
        - The condition should be stateless and only depend on the current state.
        - DO NOT use any side effects in the condition (e.g., network calls, database queries).
        - The condition should be a pure function of the state.

        .. code-block:: python

            class MyCondition(Condition[MyState]):
                def evaluate(self, state: MyState) -> bool: # implement the abstract method
                    return state.some_property == "some_value"

            my_condition = MyCondition()
            edges = [
                Edge(tail=node_1, head=node_2, condition=my_condition),
                Edge(tail=node_2, head=node_3),  # No condition, (or None) means the condition is always valid
            ]
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
