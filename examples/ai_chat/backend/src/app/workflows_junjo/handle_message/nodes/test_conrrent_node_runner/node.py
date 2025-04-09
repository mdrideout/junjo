import asyncio

from junjo.node import Node
from loguru import logger

from app.workflows_junjo.handle_message.nodes.test_conrrent_node_1.node import TestConcurrentNode1
from app.workflows_junjo.handle_message.nodes.test_conrrent_node_2.node import TestConcurrentNode2
from app.workflows_junjo.handle_message.nodes.test_conrrent_node_3.node import TestConcurrentNode3
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class TestConcurrentNodeRunner(Node[MessageWorkflowStore]):
    """Runs the test concurrent nodes."""

    async def service(self, store) -> None:
        # Test calling other nodes directly to see what happens
        logger.info("Running TestConcurrentNodeRunner")

        # Test setting state before
        await store.append_test_update("TestConcurrentNodeRunner - Before")

        # Instantiate the other concurrent nodes
        node1 = TestConcurrentNode1()
        node2 = TestConcurrentNode2()
        node3 = TestConcurrentNode3()

        # Run the service method of each node concurrently using asyncio.gather
        await asyncio.gather(
            node1.execute(store, self.id),
            node2.execute(store, self.id),
            node3.execute(store, self.id),
        )

        # Test setting state after
        await store.append_test_update("TestConcurrentNodeRunner - After")


        logger.info("Finished running TestConcurrentNodeRunner")

        return
