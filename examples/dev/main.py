


from examples.dev.store import MyGraphState, MyGraphStore
from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import BaseNode
from junjo.workflow import Workflow
from junjo.workflow_context import WorkflowContextManager

# Run With
# python -m examples.dev.main
# uv run -m examples.dev.main

async def main():
    """The main entry point for the application."""

    # Initialize a workflow context manager
    WorkflowContextManager()

    # Initialize a store
    initial_state = MyGraphState(items=["apple", "banana", "cherry"], counter=0, includeWarning=False)
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

    class CountNode(BaseNode[MyGraphState, MyGraphStore]):
        """Workflow node that counts items"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            print("Running CountNode service from initial state: ", state.model_dump())

            items = state.items
            count = await count_items(items)
            return store.set_counter(count)


    class FinalNode(BaseNode[MyGraphState, MyGraphStore]):
        """Workflow node that prints the final state"""

        async def service(self, state: MyGraphState, store: MyGraphStore) -> MyGraphState:
            print("Running FinalNode service from initial state: ", state.model_dump())
            return state

    count_node = CountNode()
    final_node = FinalNode()

    # Construct a Graph
    graph = Graph(
        source=count_node,
        sink=final_node,
        edges=[
            Edge(tail=count_node, head=final_node),
        ]
    )

    workflow = Workflow(graph=graph, initial_store=graph_store)
    print("Executing the workflow with initial store state: ", workflow.get_state)
    await workflow.execute()
    final_state = workflow.get_state
    print(f"Final state: {final_state}")

    # Cleanup
    unsubscribe()


    # def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
    #     return context.get("result", 0) > 10

    # workflow_graph = Graph(
    #     source=node1,
    #     sink=final_node,
    #     edges=[
    #         Edge(tail=node1, head=final_node),
    #         # Edge(tail=node2, head=node3, condition=condition1),
    #         # Edge(tail=node2, head=final_node),
    #         # Edge(tail=node3, head=final_node),
    #     ]
    # )

    # print(workflow_graph.to_mermaid())
    # print(workflow_graph.to_dot_notation())
    # graph_to_graphviz_image(workflow_graph)

    # workflow = Workflow(workflow_graph)
    # await workflow.execute()
    # print(f"Final Context: {workflow.context}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
