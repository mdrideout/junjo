import asyncio
import os
from dotenv import load_dotenv
from loguru import logger
from junjo import BaseState, BaseStore, Edge, Graph, Node, Workflow
from otel_config import setup_telemetry

# Load environment variables from .env file
load_dotenv()

# Setup telemetry
if not setup_telemetry():
    # If telemetry setup failed (missing API key), do not run the app.
    # Instead, keep the container alive but dormant to avoid restart loops.
    # Re-check/re-log every 60 seconds.
    while True:
        import time

        time.sleep(30)
        setup_telemetry()

# --- Junjo Workflow Definition ---


# 1. Define the State
class AppState(BaseState):
    counter: int = 0


# 2. Define the Store
class AppStore(BaseStore[AppState]):
    async def increment_counter(self):
        await self.set_state({"counter": self._state.counter + 1})


# 3. Define the Nodes
class StartNode(Node[AppStore]):
    async def service(self, store: AppStore):
        logger.info("Workflow started.")
        await asyncio.sleep(1)


class IncrementNode(Node[AppStore]):
    async def service(self, store: AppStore):
        await store.increment_counter()
        state = await store.get_state()
        logger.info(f"Counter incremented to: {state.counter}")
        await asyncio.sleep(1)


class EndNode(Node[AppStore]):
    async def service(self, store: AppStore):
        logger.info("Workflow finished.")
        await asyncio.sleep(1)


# 4. Define the Graph Factory
def create_app_graph():
    """Factory function that creates a new graph instance for each workflow execution."""
    # Instantiate Nodes
    start_node = StartNode()
    increment_node = IncrementNode()
    end_node = EndNode()

    # Create and return the Graph
    return Graph(
        source=start_node,
        sink=end_node,
        edges=[
            Edge(tail=start_node, head=increment_node),
            Edge(tail=increment_node, head=end_node),
        ],
    )


# 5. Create the Workflow Factory
def create_app_workflow():
    """Factory function that creates a new workflow instance for each execution."""
    return Workflow[AppState, AppStore](
        name="Example Deployment Workflow",
        graph_factory=create_app_graph,
        store_factory=lambda: AppStore(initial_state=AppState()),
    )


# --- Main Execution Loop ---
async def main():
    """Runs the workflow in a loop to continuously generate telemetry."""
    logger.info("Starting Junjo application...")
    while True:
        logger.info("Executing workflow...")
        workflow = create_app_workflow()
        await workflow.execute()
        final_state = await workflow.get_state_json()
        logger.success(f"Final state: {final_state}")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
