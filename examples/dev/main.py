

from pydantic import BaseModel

from examples.dev.store import GraphState, GraphStateActions, GraphStore
from junjo.edge import Edge
from junjo.graphviz.utils import graph_to_graphviz_image
from junjo.node import Node
from junjo.workflow import Graph, Workflow

# Run With
# python -m examples.dev.main
# uv run -m examples.dev.main

async def main():
    """The main entry point for the application."""

    # Store Testing
    # Instantiate the GraphStore
    graph_store = GraphStore()

    # Subscribe to state changes
    def on_state_change(new_state: GraphState):
        print("State changed:", new_state.model_dump())
    unsubscribe = graph_store.subscribe(on_state_change)

    # Dispatch a change to the store
    graph_store.dispatch(action=GraphStateActions.INCREMENT)
    graph_store.dispatch(action=GraphStateActions.SET_COUNTER, payload=5)
    graph_store.dispatch(action=GraphStateActions.SET_LOADING, payload=True)
    graph_store.dispatch(action=GraphStateActions.DECREMENT)
    graph_store.dispatch(action=GraphStateActions.SET_LOADING, payload=False)

    # Cleanup
    unsubscribe()



    # Graph Testing
    class MyInput(BaseModel):
        text: str

    class MyOutput(BaseModel):
        text_lengths: dict[str, int]


    # TODO: Update node to pass an action to the node that
    # allows the state to be updated with the result of the logic function

    async def logic_fn(data: MyInput) -> MyOutput:
        # Some asynchronous processing or I/O could happen here.
        # For demonstration, we'll just return the length of the input text.
        await asyncio.sleep(0.25)  # Simulate async delay
        return MyOutput(text_lengths={data.text: len(data.text)})

    async def final_logic_fn(data: MyInput) -> MyOutput:
        # Some asynchronous processing or I/O could happen here.
        # For demonstration, we'll just return the length of the input text.
        await asyncio.sleep(0.25)
        return MyOutput(text_lengths={f"Final {data.text})": len(data.text)})


    node1 = Node[MyInput, MyOutput](
        logic=logic_fn
    )

    final_node = Node[MyInput, MyOutput](
        # Inline logic function
        logic=final_logic_fn
    )









    # def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
    #     return context.get("result", 0) > 10

    workflow_graph = Graph(
        source=node1,
        sink=final_node,
        edges=[
            Edge(tail=node1, head=final_node),
            # Edge(tail=node2, head=node3, condition=condition1),
            # Edge(tail=node2, head=final_node),
            # Edge(tail=node3, head=final_node),
        ]
    )

    print(workflow_graph.to_mermaid())
    print(workflow_graph.to_dot_notation())
    graph_to_graphviz_image(workflow_graph)

    workflow = Workflow(workflow_graph)
    await workflow.execute()
    print(f"Final Context: {workflow.context}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
