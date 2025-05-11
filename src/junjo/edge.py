


from .condition import Condition
from .node import Node
from .store import BaseStore, StateT
from .workflow import _NestableWorkflow


class Edge:
    """
    Represents a directed edge in the workflow graph.

    An edge connects a tail node to a head node, optionally with a condition
    that determines whether the transition from tail to head should occur.
    """

    def __init__(
        self,
        tail: Node | _NestableWorkflow,
        head: Node | _NestableWorkflow,
        condition: Condition[StateT] | None = None,
    ):
        """
        Args:
            tail: The source node of the edge (where the transition originates).
            head: The destination node of the edge (where the transition leads).
            condition (Condition[StateT]): An optional function that determines whether the transition
                       from tail to head should occur. If None, the transition is always valid.
        """

        self.tail = tail
        self.head = head
        self.condition = condition

    async def next_node(self, store: BaseStore) -> Node | _NestableWorkflow | None:
        """
        Determines the next node in the workflow based on the edge's condition (Condition[StateT]).

        Args:
            store (BaseStore): The store instance to use for resolving the next node.

        Returns:
            The next node if the transition is valid, otherwise None.
        """
        if self.condition is None:
            return self.head
        else:
            state = await store.get_state()
            if state is None:
                raise ValueError("State is not available in the store.")

            return self.head if self.condition.evaluate(state) else None
