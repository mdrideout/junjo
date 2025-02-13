from typing import Any

from junjo.edge import Edge
from junjo.node import Node
from junjo.workflow import Graph, Workflow

# Run With
# python -m examples.dev.main
# uv run -m examples.dev.main

async def main():
    """The main entry point for the application."""

    class MyNode(Node):
        async def execute(self):
            self._outputs["result"] = self._inputs["a"] + self._inputs["b"]
            print(f"MyNode Result: {self._outputs['result']}")

    class MyNode2(Node):
        async def execute(self):
            self._outputs["result"] = self._inputs["c"] * self._inputs["d"]
            print(f"MyNode2 Result: {self._outputs['result']}")

    class MyNode3(Node):
        async def execute(self):
            self._outputs["result"] = self._inputs["e"] - self._inputs["f"]
            print(f"MyNode3 Result: {self._outputs['result']}")

    class FinalNode(Node):
        async def execute(self):
            print("Final Node Executed")

    node1 = MyNode(a=1, b=2)
    node2 = MyNode2(c=3, d=4)
    node3 = MyNode3(e=5, f=6)
    final_node = FinalNode()


    def condition1(current_node: Node, next_node: Node, context: dict[str, Any]) -> bool:
        return context.get("result", 0) > 10

    workflow_graph = Graph(
        source=node1,
        sink=final_node,
        edges=[
            Edge(tail=node1, head=node2),
            Edge(tail=node2, head=node3, condition=condition1),
            Edge(tail=node2, head=final_node),
            Edge(tail=node3, head=final_node),
        ]
    )
    print(workflow_graph.to_mermaid())

    workflow = Workflow(workflow_graph)
    await workflow.execute()
    print(f"Final Context: {workflow.context}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
