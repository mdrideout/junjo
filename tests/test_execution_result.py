import builtins
from dataclasses import FrozenInstanceError

import pytest

from junjo import BaseState, BaseStore, Edge, ExecutionResult, Graph, Node, Subflow, Workflow


class WorkflowState(BaseState):
    status: str = "pending"


class WorkflowStore(BaseStore[WorkflowState]):
    async def set_status(self, status: str) -> None:
        await self.set_state({"status": status})


class SetWorkflowStatusNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.set_status("completed")


def create_single_node_workflow_graph() -> Graph:
    node = SetWorkflowStatusNode()
    return Graph(source=node, sinks=[node], edges=[])


class SubflowParentState(BaseState):
    label: str


class SubflowParentStore(BaseStore[SubflowParentState]):
    pass


class SubflowState(BaseState):
    label: str | None = None
    completed: bool = False


class SubflowStore(BaseStore[SubflowState]):
    async def set_label(self, label: str) -> None:
        await self.set_state({"label": label})

    async def mark_completed(self) -> None:
        await self.set_state({"completed": True})


class CompleteSubflowNode(Node[SubflowStore]):
    async def service(self, store: SubflowStore) -> None:
        await store.mark_completed()


def create_single_node_subflow_graph() -> Graph:
    node = CompleteSubflowNode()
    return Graph(source=node, sinks=[node], edges=[])


class ExampleSubflow(
    Subflow[SubflowState, SubflowStore, SubflowParentState, SubflowParentStore]
):
    async def pre_run_actions(
        self,
        parent_store: SubflowParentStore,
        subflow_store: SubflowStore,
    ) -> None:
        parent_state = await parent_store.get_state()
        await subflow_store.set_label(parent_state.label)

    async def post_run_actions(
        self,
        parent_store: SubflowParentStore,
        subflow_store: SubflowStore,
    ) -> None:
        return


class ScopeParentState(BaseState):
    pass


class ScopeParentStore(BaseStore[ScopeParentState]):
    pass


class ScopeChildState(BaseState):
    pass


class ScopeChildStore(BaseStore[ScopeChildState]):
    pass


class FirstScopeChildNode(Node[ScopeChildStore]):
    async def service(self, store: ScopeChildStore) -> None:
        return


class SecondScopeChildNode(Node[ScopeChildStore]):
    async def service(self, store: ScopeChildStore) -> None:
        return


def create_scope_child_graph() -> Graph:
    first = FirstScopeChildNode()
    second = SecondScopeChildNode()
    return Graph(source=first, sinks=[second], edges=[Edge(tail=first, head=second)])


class ScopeSubflow(
    Subflow[ScopeChildState, ScopeChildStore, ScopeParentState, ScopeParentStore]
):
    async def pre_run_actions(
        self,
        parent_store: ScopeParentStore,
        subflow_store: ScopeChildStore,
    ) -> None:
        return

    async def post_run_actions(
        self,
        parent_store: ScopeParentStore,
        subflow_store: ScopeChildStore,
    ) -> None:
        return


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


@pytest.mark.asyncio
async def test_workflow_execute_returns_execution_result_with_final_state() -> None:
    workflow = Workflow[WorkflowState, WorkflowStore](
        graph_factory=create_single_node_workflow_graph,
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState()),
    )

    result = await workflow.execute()

    assert isinstance(result, ExecutionResult)
    assert result.run_id
    assert result.definition_id == workflow.id
    assert result.name == workflow.name
    assert result.state.status == "completed"
    assert sum(result.node_execution_counts.values()) == 1


@pytest.mark.asyncio
async def test_subflow_execute_returns_execution_result() -> None:
    subflow = ExampleSubflow(
        graph_factory=create_single_node_subflow_graph,
        store_factory=lambda: SubflowStore(initial_state=SubflowState()),
    )
    parent_store = SubflowParentStore(
        initial_state=SubflowParentState(label="from-parent"),
    )

    result = await subflow.execute(parent_store=parent_store, parent_id="parent-id")

    assert isinstance(result, ExecutionResult)
    assert result.run_id
    assert result.definition_id == subflow.id
    assert result.name == subflow.name
    assert result.state.label == "from-parent"
    assert result.state.completed is True


@pytest.mark.asyncio
async def test_execution_result_node_execution_counts_are_current_scope_only() -> None:
    subflow = ScopeSubflow(
        graph_factory=create_scope_child_graph,
        store_factory=lambda: ScopeChildStore(initial_state=ScopeChildState()),
    )
    workflow = Workflow[ScopeParentState, ScopeParentStore](
        graph_factory=lambda: Graph(source=subflow, sinks=[subflow], edges=[]),
        store_factory=lambda: ScopeParentStore(initial_state=ScopeParentState()),
    )

    workflow_result = await workflow.execute()
    subflow_result = await subflow.execute(
        parent_store=ScopeParentStore(initial_state=ScopeParentState()),
        parent_id="parent-id",
    )

    assert workflow_result.node_execution_counts == {subflow.id: 1}
    assert len(workflow_result.node_execution_counts) == 1
    assert len(subflow_result.node_execution_counts) == 2
    assert sum(subflow_result.node_execution_counts.values()) == 2


@pytest.mark.asyncio
async def test_execution_result_is_immutable_and_hides_runtime_details() -> None:
    workflow = Workflow[WorkflowState, WorkflowStore](
        graph_factory=create_single_node_workflow_graph,
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState()),
    )

    result = await workflow.execute()

    with pytest.raises(FrozenInstanceError):
        result.name = "renamed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.state = WorkflowState(status="replaced")  # type: ignore[misc]

    with pytest.raises(TypeError):
        result.node_execution_counts["another-node"] = 1

    assert not hasattr(result, "store")
    assert not hasattr(result, "graph")
