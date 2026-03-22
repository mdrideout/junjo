


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
        :param tail: The source node of the edge where the transition
            originates.
        :type tail: Node | _NestableWorkflow
        :param head: The destination node of the edge where the transition
            leads.
        :type head: Node | _NestableWorkflow
        :param condition: An optional condition that determines whether the
            transition from ``tail`` to ``head`` should occur. If ``None``, the
            transition is always valid.
        :type condition: Condition[StateT] | None
        """

        self.tail = tail
        self.head = head
        self.condition = condition

    async def next_node(self, store: BaseStore) -> Node | _NestableWorkflow | None:
        """
        Determine the next node in the workflow based on this edge's
        condition.

        :param store: The store instance to use when resolving the next node.
        :type store: BaseStore
        :returns: The next node if the transition is valid, otherwise ``None``.
        :rtype: Node | _NestableWorkflow | None
        """
        if self.condition is None:
            return self.head
        else:
            state = await store.get_state()
            if state is None:
                raise ValueError("State is not available in the store.")

            return self.head if self.condition.evaluate(state) else None
