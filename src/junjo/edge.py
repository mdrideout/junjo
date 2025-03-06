from collections.abc import Callable

from junjo.node import Node
from junjo.store import StoreT
from junjo.workflow_context import WorkflowContextManager


class Edge:
    """
    Represents a directed edge in the workflow graph.

    An edge connects a tail node to a head node, optionally with a condition
    that determines whether the transition from tail to head should occur.
    """

    def __init__(
        self,
        tail: Node,
        head: Node,
        condition: Callable[[Node, Node, StoreT], bool] | None = None,
    ):
        """
        Initializes the Edge.

        Args:
            tail: The source node of the edge (where the transition originates).
            head: The destination node of the edge (where the transition leads).
            condition: An optional function that determines whether the transition
                       from tail to head should occur.  The function should take
                       three arguments: the tail node, the head node, and the
                       current workflow context, and return True if the transition
                       is valid, False otherwise.
        """

        self.tail = tail
        self.head = head
        self.condition = condition

    def next_node(self, workflow_id: str) -> Node | None:
        """
        Determines the next node in the workflow based on the edge's condition.

        Args:
            context: The current workflow context (a dictionary).

        Returns:
            The next node if the transition is valid, otherwise None.
        """
        if self.condition is None:
            return self.head
        else:
            store = WorkflowContextManager.get_store(workflow_id)
            if store is None:
                raise ValueError("Store is not available in the context.")

            state = store.get_state()
            if state is None:
                raise ValueError("State is not available in the store.")

            return self.head if self.condition(self.tail, self.head, state) else None
