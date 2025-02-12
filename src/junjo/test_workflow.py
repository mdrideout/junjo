import unittest
from typing import Any

from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node
from junjo.workflow import Workflow


class MockNode(Node):
    async def execute(self):
        pass


class TestWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_max_iterations_exceeded(self):
        """Test that a ValueError is raised if max_iterations is exceeded."""
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode()  # Sink node

        # Create edges; condition always returns True to create a loop
        def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
            return True

        edges = [
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=node1, condition=condition1),
            Edge(tail=node1, head=final_node)
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        workflow = Workflow(workflow_graph, max_iterations=2)  # Set a low max_iterations for testing

        with self.assertRaises(ValueError) as context:
            await workflow.execute()
        #Check only the beginning of the string
        self.assertTrue(str(context.exception).startswith("Node '<MockNode"))

if __name__ == "__main__":
    unittest.main()
