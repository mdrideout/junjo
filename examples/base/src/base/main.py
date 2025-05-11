from base.store import MyGraphState, MyGraphStore
from junjo import Condition, Edge, Graph, Node, Workflow
from junjo.telemetry.hook_manager import HookManager


async def main():
    """The main entry point for the application."""

    # Initialize a store
    initial_state = MyGraphState(items=["apple", "banana", "cherry"], counter=0, warning=False)
    graph_store = MyGraphStore(initial_state=initial_state)

    # Subscribe to state changes
    def on_state_change(new_state: MyGraphState):
        print("State changed:", new_state.model_dump())
    unsubscribe = await graph_store.subscribe(on_state_change)

    # Example service function
    async def count_items(items: list[str]) -> int:
        print("Running count_items...")

        count = len(items)
        return count

    class CountNode(Node[MyGraphStore]):
        """Workflow node that counts items"""

        async def service(self, store: MyGraphStore) -> None:
            state = await store.get_state()
            print("Running CountNode service from initial state: ", state.model_dump())
            items = state.items
            count = await count_items(items)
            store.set_counter(count)
            return

    class IncrementNode(Node[MyGraphStore]):
        """Workflow node that increments the counter"""

        async def service(self, store: MyGraphStore) -> None:
            store.set_counter(12)
            return

    class SetWarningNode(Node[MyGraphStore]):
        """Workflow node that sets the warning flag"""

        async def service(self, store: MyGraphStore) -> None:
            store.set_warning(True)
            return

    class FinalNode(Node[MyGraphStore]):
        """Workflow node that prints the final state"""

        async def service(self, store: MyGraphStore) -> None:
            state = await store.get_state()
            print("Running FinalNode service from initial state: ", state.model_dump())
            return

    class CountOver10Condition(Condition[MyGraphState]):
        def evaluate(self, state: MyGraphState) -> bool:
            return state.counter > 10

    count_over_10 = CountOver10Condition()

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

    # Currently broken
    # print(f"ReactFlow:\n{graph.to_react_flow().model_dump_json()}\n")
    # print(f"Mermaid:\n{graph.to_mermaid()}")
    # print(f"Graphviz:\n{graph.to_dot_notation()}")

    workflow = Workflow[MyGraphState, MyGraphStore](
        name="demo_base_workflow",
        graph=graph,
        store=graph_store,
        hook_manager=HookManager(verbose_logging=False, open_telemetry=True),
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
