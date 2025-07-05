import asyncio
import os
from dotenv import load_dotenv
from junjo import BaseState, BaseStore, Edge, Graph, Node, Workflow
from otel_config import setup_telemetry

# Load environment variables from .env file
load_dotenv()

# Setup telemetry
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
        print("Workflow started.")
        await asyncio.sleep(1)

class IncrementNode(Node[AppStore]):
    async def service(self, store: AppStore):
        await store.increment_counter()
        state = await store.get_state()
        print(f"Counter incremented to: {state.counter}")
        await asyncio.sleep(1)

class EndNode(Node[AppStore]):
    async def service(self, store: AppStore):
        print("Workflow finished.")
        await asyncio.sleep(1)

# 4. Instantiate Nodes
start_node = StartNode()
increment_node = IncrementNode()
end_node = EndNode()

# 5. Define the Graph
app_graph = Graph(
    source=start_node,
    sink=end_node,
    edges=[
        Edge(tail=start_node, head=increment_node),
        Edge(tail=increment_node, head=end_node),
    ]
)

# 6. Create the Workflow
app_workflow = Workflow[AppState, AppStore](
    name="Example Deployment Workflow",
    graph=app_graph,
    store_factory=lambda: AppStore(initial_state=AppState())
)

# --- Main Execution Loop ---
async def main():
    """Runs the workflow in a loop to continuously generate telemetry."""
    print("Starting Junjo application...")
    while True:
        print("\nExecuting workflow...")
        await app_workflow.execute()
        final_state = await app_workflow.get_state_json()
        print(f"Final state: {final_state}")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())