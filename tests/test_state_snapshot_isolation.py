import builtins

import pytest

from junjo import BaseState, BaseStore, Graph, Node, Workflow


class SnapshotState(BaseState):
    items: list[int]
    metadata: dict[str, str]


class SnapshotStore(BaseStore[SnapshotState]):
    pass


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


@pytest.mark.asyncio
async def test_store_get_state_returns_detached_nested_snapshot() -> None:
    store = SnapshotStore(
        initial_state=SnapshotState(items=[1, 2], metadata={"status": "ready"}),
    )

    snapshot = await store.get_state()
    snapshot.items.append(3)
    snapshot.metadata["status"] = "mutated"

    current_state = await store.get_state()

    assert current_state.items == [1, 2]
    assert current_state.metadata == {"status": "ready"}


class MutateNestedStateNode(Node[SnapshotStore]):
    async def service(self, store: SnapshotStore) -> None:
        state = await store.get_state()
        state.items.append(99)
        state.metadata["status"] = "leaked"


@pytest.mark.asyncio
async def test_execution_result_state_is_detached_from_internal_store_snapshot() -> None:
    created_stores: list[SnapshotStore] = []

    def create_store() -> SnapshotStore:
        store = SnapshotStore(
            initial_state=SnapshotState(items=[1], metadata={"status": "ready"}),
        )
        created_stores.append(store)
        return store

    node = MutateNestedStateNode()
    workflow = Workflow[SnapshotState, SnapshotStore](
        graph_factory=lambda: Graph(source=node, sink=node, edges=[]),
        store_factory=create_store,
    )

    result = await workflow.execute()

    assert len(created_stores) == 1

    internal_state = await created_stores[0].get_state()

    assert result.state.items == [1]
    assert result.state.metadata == {"status": "ready"}
    assert internal_state.items == [1]
    assert internal_state.metadata == {"status": "ready"}

    # Mutating the result snapshot must not mutate the internal store.
    result.state.items.append(2)
    result.state.metadata["status"] = "changed-after-run"

    internal_state_after = await created_stores[0].get_state()

    assert internal_state_after.items == [1]
    assert internal_state_after.metadata == {"status": "ready"}
