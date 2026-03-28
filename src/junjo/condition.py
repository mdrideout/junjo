from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .state import BaseState

StateT = TypeVar("StateT", bound=BaseState)

class Condition(Generic[StateT], ABC):
    """
    Abstract base class for edge conditions in a workflow graph.

    Implement a concrete condition that determines whether a transition along
    an edge should occur based only on the current state.

    This is designed to be used with the :class:`~junjo.Edge` class, which
    represents a directed edge in the workflow graph. The condition is
    evaluated when determining whether to transition from the tail node to the
    head node.

    ``StateT`` is the state type that the condition evaluates against. It
    should be a subclass of :class:`~junjo.BaseState`.

    Conditions should follow these rules:

    - The condition should be stateless and depend only on the current state.
    - Do not use side effects in the condition, such as network calls or
      database queries.
    - The condition should be a pure function of the state.

    .. rubric:: Example

    .. code-block:: python

        class MyCondition(Condition[MyState]):
            def evaluate(self, state: MyState) -> bool:
                return state.some_property == "some_value"

        my_condition = MyCondition()
        edges = [
            Edge(tail=node_1, head=node_2, condition=my_condition),
            Edge(tail=node_2, head=node_3),
        ]
    """

    @abstractmethod
    def evaluate(self, state: StateT) -> bool:
        """
        Evaluate whether the transition should occur based on the current
        workflow state.

        :param state: The current workflow state.
        :type state: StateT
        :returns: ``True`` if the transition should occur, ``False`` otherwise.
        :rtype: bool
        """
        pass

    def __str__(self) -> str:
        """
        Default string representation of the condition.
        Subclasses can override this for more specific representations.
        """
        return self.__class__.__name__
