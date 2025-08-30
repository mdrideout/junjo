import unittest

from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node
from junjo.state import BaseState
from junjo.store import BaseStore
from junjo.workflow import Workflow


class MockState(BaseState):
    pass

class MockStore(BaseStore[MockState]):
    pass

class MockNode(Node[MockStore]):
    async def service(self, store: MockStore) -> None:
        pass

class TestWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_max_iterations_exceeded(self):
        """Test that a ValueError is raised if max_iterations is exceeded."""
        def create_graph() -> Graph:
            node1 = MockNode()
            node2 = MockNode()
            final_node = MockNode()  # Sink node

            edges = [
                Edge(tail=node1, head=node2),
                Edge(tail=node2, head=node1),
                Edge(tail=node1, head=final_node)
            ]

            return Graph(source=node1, sink=final_node, edges=edges)

        workflow = Workflow[MockState, MockStore](
            graph_factory=create_graph,
            store_factory=lambda: MockStore(initial_state=MockState()),
            max_iterations=2 # Set a low max_iterations for testing
        )

        with self.assertRaises(ValueError) as context:
            await workflow.execute()
        self.assertTrue(str(context.exception).startswith("Node '<MockNode"))

    async def test_unreached_sink_raises_exception(self):
        """Test that an unreachable sink raises an exception."""
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode()

        edges = [
            Edge(tail=node1, head=node2),
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        store = MockStore(initial_state=MockState())

        with self.assertRaises(ValueError) as context:
            await workflow_graph.get_next_node(store, node2)
        self.assertTrue(str(context.exception).startswith("Check your Graph. No resolved edges."))


if __name__ == "__main__":
    unittest.main()
