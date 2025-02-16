import pytest
from pydantic import BaseModel

from junjo.node import Node
from junjo.store.store import BaseStore
from junjo.workflow_context import WorkflowContextManager


class DummyState(BaseModel):
    pass


class DummyStore(BaseStore):
    def get_state(self) -> BaseModel:
        return DummyState()


class MyNode(Node):
    async def service(self, state: DummyState, store: DummyStore) -> DummyState:
        return state

@pytest.mark.asyncio
async def test_node_service_wrong_state_param():
    """Throws ValueError if state is not a subclass of StateT."""
    class MyNodeWithWrongState(Node):
        async def service(self, state: str, store: DummyStore) -> DummyState: # type: ignore
            pass

    node = MyNodeWithWrongState()
    with pytest.raises(ValueError, match="Service function must have a 'state' parameter of type"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_wrong_store_param():
    """Throws ValueError if store is not a subclass of StoreT."""
    class MyNodeWithWrongStore(Node):
        async def service(self, state: DummyState, store: str) -> DummyState: # type: ignore
            pass

    node = MyNodeWithWrongStore()
    with pytest.raises(ValueError, match="Service function must have a 'store' parameter of type"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_wrong_return_type():
    """Throws ValueError if return type is not a subclass of StateT."""
    class MyNodeWithWrongReturnType(Node):
        async def service(self, state: DummyState, store: DummyStore) -> str:
            return "wrong_return_type"

    node = MyNodeWithWrongReturnType()
    with pytest.raises(ValueError, match="Service function must have a return type of"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_return_type():
    """Throws ValueError if return type is not specified."""
    class MyNodeWithMissingReturnType(Node):
        async def service(self, state: DummyState, store: DummyStore):
            pass

    node = MyNodeWithMissingReturnType()
    with pytest.raises(ValueError, match="Service function must have a return type of"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_store_param():
    """Throws ValueError if store parameter is missing."""
    class MyNodeWithMissingStore(Node):
        async def service(self, state: DummyState) -> DummyState: # type: ignore
            pass

    node = MyNodeWithMissingStore()
    with pytest.raises(ValueError, match="Service function must have a 'store' parameter of type"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_service_missing_state_param():
    """Throws ValueError if state parameter is missing."""
    class MyNodeWithMissingState(Node):
        async def service(self, store: DummyStore) -> DummyState: # type: ignore
            pass

    node = MyNodeWithMissingState()
    with pytest.raises(ValueError, match="Service function must have a 'state' parameter of type"):
        await node._execute("dummy_workflow_id")

@pytest.mark.asyncio
async def test_node_id():
    """Returns the unique identifier for the node."""
    node = MyNode()
    assert node.id
    assert isinstance(node.id, str)
