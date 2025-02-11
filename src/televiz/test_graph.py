import unittest
from typing import Any
from unittest.mock import AsyncMock

from televiz.edge import Edge
from televiz.graph import Graph
from televiz.node import Node


class MockNode(Node):
    async def execute(self):
        pass


class TestGraph(unittest.IsolatedAsyncioTestCase):
    async def test_unreached_sink_raises_exception(self):
        """Test that an exception is raised if the sink node is unreachable."""

        # Create Mock Nodes
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode() #Sink Node

        node1.execute = AsyncMock()
        node2.execute = AsyncMock()
        final_node.execute = AsyncMock()

        # Create edges, condition1 is always false
        def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
            return False

        edges = [
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=final_node, condition=condition1),
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        with self.assertRaises(ValueError) as context:
            workflow_graph.get_next_node(node2, {}) #Test this edge, with condition1
        self.assertTrue(str(context.exception).startswith("No valid transition found for node '<MockNode"))



    async def test_reachable_sink_does_not_raise_exception(self):
        """Test that no exception is raised if the sink node is reachable."""
        # Create Mock Nodes
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode() #Sink Node

        node1.execute = AsyncMock()
        node2.execute = AsyncMock()
        final_node.execute = AsyncMock()

        # Create edges, condition1 is always true
        def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
            return True

        edges = [
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=final_node, condition=condition1),
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        next_node = workflow_graph.get_next_node(node2, {})
        self.assertEqual(next_node, final_node)

if __name__ == "__main__":
    unittest.main()
