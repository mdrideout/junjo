import unittest
from contextvars import ContextVar
from unittest.mock import patch

from pydantic import BaseModel

from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node
from junjo.store import BaseStore
from junjo.workflow import Workflow
from junjo.workflow_context import WorkflowContextManager


class MockState(BaseModel):
    pass

class MockStore(BaseStore):
    def get_state(self) -> BaseModel:
        return MockState()

class MockNode(Node):
    async def service(self, state: MockState, store: MockStore) -> MockState:
        return state

class TestWorkflow(unittest.IsolatedAsyncioTestCase):
    @patch.object(WorkflowContextManager, '_store_dict_var', new_callable=lambda: ContextVar("store_dict", default={}))
    async def test_max_iterations_exceeded(self, mock_store_dict_var):
        """Test that a ValueError is raised if max_iterations is exceeded."""
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode()  # Sink node

        # Create edges; condition always returns True to create a loop
        def condition(current_node: Node, next_node: Node, state: MockState) -> bool:
            return True

        edges = [
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=node1, condition=condition),
            Edge(tail=node1, head=final_node)
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        workflow = Workflow(
            workflow_graph,
            initial_store=MockStore(initial_state=MockState()),
            max_iterations=2 # Set a low max_iterations for testing
        )

        with self.assertRaises(ValueError) as context:
            await workflow.execute()
        #Check only the beginning of the string
        self.assertTrue(str(context.exception).startswith("Node '<MockNode"))

    @patch.object(WorkflowContextManager, '_store_dict_var', new_callable=lambda: ContextVar("store_dict", default={}))
    async def test_unreached_sink_raises_exception(self, mock_store_dict_var):
        """Test that an unreachable sink raises an exception."""
        node1 = MockNode()
        node2 = MockNode()
        final_node = MockNode()

        def condition(current_node: Node, next_node: Node, state: MockState) -> bool:
            return False

        edges = [
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=node1, condition=condition), # Condition should not allow back to node1
            Edge(tail=node1, head=final_node)
        ]

        workflow_graph = Graph(source=node1, sink=final_node, edges=edges)
        WorkflowContextManager.set_store("workflow_id", MockStore(initial_state=MockState()))

        with self.assertRaises(ValueError) as context:
            workflow_graph.get_next_node("workflow_id", node2)
        self.assertTrue(str(context.exception).startswith("No valid transition found for node '<MockNode"))


if __name__ == "__main__":
    unittest.main()
