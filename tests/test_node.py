import pytest
from pydantic import BaseModel

from junjo.node import Node
from junjo.store import BaseStore


class MockState(BaseModel):
    pass


class MockStore(BaseStore):
    def get_state(self) -> BaseModel:
        return MockState()


class MockNode(Node):
    async def service(self, state: MockState, store: MockStore) -> MockState:
        return state

@pytest.mark.asyncio
async def test_node_service_wrong_state_param():
    """Throws ValueError if state is not a subclass of StateT."""
    class MockNodeWithWrongState(Node):
        async def service(self, state: str, store: MockStore) -> MockState: # type: ignore
            pass

    node = MockNodeWithWrongState()
    with pytest.raises(ValueError, match="Service function must have a 'state' parameter of type"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_wrong_store_param():
    """Throws ValueError if store is not a subclass of StoreT."""
    class MockNodeWithWrongStore(Node):
        async def service(self, state: MockState, store: str) -> MockState: # type: ignore
            pass

    node = MockNodeWithWrongStore()
    with pytest.raises(ValueError, match="Service function must have a 'store' parameter of type"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_wrong_return_type():
    """Throws ValueError if return type is not a subclass of StateT."""
    class MockNodeWithWrongReturnType(Node):
        async def service(self, state: MockState, store: MockStore) -> str:
            return "wrong_return_type"

    node = MockNodeWithWrongReturnType()
    with pytest.raises(ValueError, match="Service function must have a return type of"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_return_type():
    """Throws ValueError if return type is not specified."""
    class MockNodeWithMissingReturnType(Node):
        async def service(self, state: MockState, store: MockStore):
            pass

    node = MockNodeWithMissingReturnType()
    with pytest.raises(ValueError, match="Service function must have a return type of"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_store_param():
    """Throws ValueError if store parameter is missing."""
    class MockNodeWithMissingStore(Node):
        async def service(self, state: MockState) -> MockState: # type: ignore
            pass

    node = MockNodeWithMissingStore()
    with pytest.raises(ValueError, match="Service function must have a 'store' parameter of type"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_state_param():
    """Throws ValueError if state parameter is missing."""
    class MockNodeWithMissingState(Node):
        async def service(self, store: MockStore) -> MockState: # type: ignore
            pass

    node = MockNodeWithMissingState()
    with pytest.raises(ValueError, match="Service function must have a 'state' parameter of type"):
        await node.execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_id():
    """Returns the unique identifier for the node."""
    node = MockNode()
    assert node.id
    assert isinstance(node.id, str)
