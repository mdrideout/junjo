from base.store import MyGraphState, MyGraphStore
from junjo.app import JunjoApp
from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node
from junjo.telemetry.hook_manager import HookManager
from junjo.workflow import Workflow
from junjo.workflow_context import WorkflowContextManager


async def main():
    """The main entry point for the application."""
    # Initialize Junjo
    junjo = JunjoApp(project_name="Junjo Base Example")
    await junjo.init()

    # Initialize a workflow context manager
    WorkflowContextManager()

    # Initialize a store
    initial_state = MyGraphState(items=["apple", "banana", "cherry"], counter=0, warning=False)
    graph_store = MyGraphStore(initial_state=initial_state)

    # Subscribe to state changes
    def on_state_change(new_state: MyGraphState):
        print("State changed:", new_state.model_dump())
    unsubscribe = graph_store.subscribe(on_state_change)

    # Example service function
    async def count_items(items: list[str]) -> int:
        print("Running count_items...")

        count = len(items)
        return count

    class CountNode(Node[MyGraphState, MyGraphStore]):
        """Workflow node that counts items"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            print("Running CountNode service from initial state: ", state.model_dump())

            items = state.items
            count = await count_items(items)
            return store.set_counter(count)

    class IncrementNode(Node[MyGraphState, MyGraphStore]):
        """Workflow node that increments the counter"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            return store.set_counter(12)

    class SetWarningNode(Node[MyGraphState, MyGraphStore]):
        """Workflow node that sets the warning flag"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            return store.set_warning(True)

    class FinalNode(Node[MyGraphState, MyGraphStore]):
        """Workflow node that prints the final state"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            print("Running FinalNode service from initial state: ", state.model_dump())
            return state

    def count_over_10(current_node: Node, next_node: Node, state: MyGraphState) -> bool:
        return state.counter > 10

    # Instantiate nodes
    count_node = CountNode()
    increment_node = IncrementNode()
    set_warning_node = SetWarningNode()
    final_node = FinalNode()

    # Construct a graph
    graph = Graph(
        source=count_node,
        sink=final_node,
        edges=[
            Edge(tail=count_node, head=increment_node),
            Edge(tail=increment_node, head=set_warning_node, condition=count_over_10),
            Edge(tail=set_warning_node, head=final_node),
            Edge(tail=increment_node, head=final_node),
        ]
    )

    print(f"ReactFlow:\n{graph.to_react_flow().model_dump_json()}\n")
    print(f"Mermaid:\n{graph.to_mermaid()}")
    print(f"Graphviz:\n{graph.to_dot_notation()}")

    workflow = Workflow(
        graph=graph,
        initial_store=graph_store,
        hook_manager=HookManager(verbose_logging=True, open_telemetry=True),
    )
    print("Executing the workflow with initial store state: ", workflow.get_state)
    await workflow.execute()
    final_state = workflow.get_state
    print(f"Final state: {final_state}")

    # Cleanup
    unsubscribe()

    print("Done.")

    return

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
