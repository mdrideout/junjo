import pytest

from televiz.node import Node


def test_node_inputs_kwargs():
    """Tests that keyword arguments are correctly assigned as inputs."""

    # Create a *concrete* subclass for testing purposes.  This is key.
    class ConcreteNode(Node):
        async def execute(self):
            pass

    node = ConcreteNode(a=1, b="hello")
    assert node.inputs == {"a": 1, "b": "hello"}
    assert node.a == 1 # type: ignore
    assert node.b == "hello" # type: ignore


def test_node_outputs_initial():
    """Verify the initial state of the outputs"""
    class ConcreteNode(Node):
        async def execute(self):
            pass
    node = ConcreteNode()
    assert node.outputs == {}
