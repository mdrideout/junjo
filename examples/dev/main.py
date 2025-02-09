from televiz.node import Node


async def main():
    """The main entry point for the application."""

    # Create a node
    class MyNode(Node):
        async def execute(self):
            self._outputs["result"] = self._inputs["a"] + self._inputs["b"]
            print(f"Result: {self._outputs['result']}")

    node = MyNode(a=1, b=2)
    await node.execute()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
