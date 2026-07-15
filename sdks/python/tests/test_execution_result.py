import asyncio
import builtins
from dataclasses import FrozenInstanceError

import pytest

from junjo import (
    BaseState,
    BaseStore,
    Edge,
    ExecutionResult,
    Graph,
    Node,
    Subflow,
    Workflow,
    WorkflowCancelledError,
    WorkflowExecutionError,
)


class WorkflowState(BaseState):
    status: str = "pending"


class WorkflowStore(BaseStore[WorkflowState]):
    async def set_status(self, status: str) -> None:
        await self.set_state({"status": status})


class TerminalEvidenceFailingStore(WorkflowStore):
    def __init__(self, *, initial_state: WorkflowState) -> None:
        super().__init__(initial_state=initial_state)
        self._evidence_reads = 0

    async def _get_store_owner_evidence(self):
        self._evidence_reads += 1
        if self._evidence_reads == 2:
            raise RuntimeError("terminal evidence failed")
        return await super()._get_store_owner_evidence()


class BlockingTerminalEvidenceFailingStore(WorkflowStore):
    def __init__(
        self,
        *,
        initial_state: WorkflowState,
        terminal_evidence_entered: asyncio.Event,
        release_terminal_evidence: asyncio.Event,
    ) -> None:
        super().__init__(initial_state=initial_state)
        self._evidence_reads = 0
        self._terminal_evidence_entered = terminal_evidence_entered
        self._release_terminal_evidence = release_terminal_evidence

    async def _get_store_owner_evidence(self):
        self._evidence_reads += 1
        if self._evidence_reads == 2:
            self._terminal_evidence_entered.set()
            await self._release_terminal_evidence.wait()
            raise RuntimeError("terminal evidence failed after caller cancellation")
        return await super()._get_store_owner_evidence()


class SetWorkflowStatusNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.set_status("completed")


class FailAfterStateChangeNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.set_status("failed-after-transition")
        raise LookupError("domain failure")


class BlockAfterStateChangeNode(Node[WorkflowStore]):
    def __init__(self, entered: asyncio.Event) -> None:
        super().__init__()
        self._entered = entered

    async def service(self, store: WorkflowStore) -> None:
        await store.set_status("running")
        self._entered.set()
        await asyncio.Future()


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


class ExampleSubflow(Subflow[SubflowState, SubflowStore, SubflowParentState, SubflowParentStore]):
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


class ScopeSubflow(Subflow[ScopeChildState, ScopeChildStore, ScopeParentState, ScopeParentStore]):
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


@pytest.mark.asyncio
async def test_admitted_workflow_failure_exposes_identity_state_and_original_cause() -> None:
    node = FailAfterStateChangeNode()
    workflow = Workflow[WorkflowState, WorkflowStore](
        name="Identity Failure Workflow",
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState()),
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute()

    error = raised.value
    assert error.run_id
    assert error.definition_id == workflow.id
    assert error.name == "Identity Failure Workflow"
    assert error.state.status == "failed-after-transition"
    assert error.state_is_terminal is True
    assert error.terminalization_error is None
    assert error.node_execution_counts == {}
    assert isinstance(error.__cause__, LookupError)
    assert str(error.__cause__) == "domain failure"
    with pytest.raises(TypeError):
        error.node_execution_counts["node"] = 1


@pytest.mark.asyncio
async def test_admitted_workflow_cancellation_remains_cancelled_error_with_identity() -> None:
    entered = asyncio.Event()
    node = BlockAfterStateChangeNode(entered)
    workflow = Workflow[WorkflowState, WorkflowStore](
        name="Identity Cancellation Workflow",
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState()),
    )
    task = asyncio.create_task(workflow.execute())
    await asyncio.wait_for(entered.wait(), timeout=0.2)

    task.cancel("caller stopped")
    with pytest.raises(WorkflowCancelledError, match="caller stopped") as raised:
        await task

    cancellation = raised.value
    assert isinstance(cancellation, asyncio.CancelledError)
    assert cancellation.run_id
    assert cancellation.definition_id == workflow.id
    assert cancellation.name == "Identity Cancellation Workflow"
    assert cancellation.state.status == "running"
    assert cancellation.state_is_terminal is True
    assert cancellation.terminalization_error is None
    assert isinstance(cancellation.__cause__, asyncio.CancelledError)
    assert cancellation.__cause__.args == ("caller stopped",)


@pytest.mark.asyncio
async def test_terminal_evidence_failure_after_success_retains_typed_identity() -> None:
    workflow = Workflow[WorkflowState, TerminalEvidenceFailingStore](
        graph_factory=create_single_node_workflow_graph,
        store_factory=lambda: TerminalEvidenceFailingStore(initial_state=WorkflowState()),
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute()

    error = raised.value
    assert error.run_id
    assert error.state.status == "completed"
    assert error.state_is_terminal is False
    assert isinstance(error.terminalization_error, RuntimeError)
    assert error.__cause__ is error.terminalization_error


@pytest.mark.asyncio
async def test_terminal_evidence_failure_preserves_selected_body_failure() -> None:
    node = FailAfterStateChangeNode()
    workflow = Workflow[WorkflowState, TerminalEvidenceFailingStore](
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: TerminalEvidenceFailingStore(initial_state=WorkflowState()),
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute()

    error = raised.value
    assert error.run_id
    assert error.state.status == "failed-after-transition"
    assert error.state_is_terminal is False
    assert isinstance(error.__cause__, LookupError)
    assert isinstance(error.terminalization_error, RuntimeError)


@pytest.mark.asyncio
async def test_terminal_evidence_failure_preserves_selected_cancellation() -> None:
    entered = asyncio.Event()
    node = BlockAfterStateChangeNode(entered)
    workflow = Workflow[WorkflowState, TerminalEvidenceFailingStore](
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: TerminalEvidenceFailingStore(initial_state=WorkflowState()),
    )
    task = asyncio.create_task(workflow.execute())
    await asyncio.wait_for(entered.wait(), timeout=0.2)

    task.cancel("caller stopped")
    with pytest.raises(WorkflowCancelledError, match="caller stopped") as raised:
        await task

    cancellation = raised.value
    assert cancellation.run_id
    assert cancellation.state.status == "running"
    assert cancellation.state_is_terminal is False
    assert isinstance(cancellation.__cause__, asyncio.CancelledError)
    assert isinstance(cancellation.terminalization_error, RuntimeError)


@pytest.mark.asyncio
async def test_cancellation_during_failing_terminal_evidence_remains_cancellation() -> None:
    terminal_evidence_entered = asyncio.Event()
    release_terminal_evidence = asyncio.Event()
    workflow = Workflow[WorkflowState, BlockingTerminalEvidenceFailingStore](
        graph_factory=create_single_node_workflow_graph,
        store_factory=lambda: BlockingTerminalEvidenceFailingStore(
            initial_state=WorkflowState(),
            terminal_evidence_entered=terminal_evidence_entered,
            release_terminal_evidence=release_terminal_evidence,
        ),
    )
    task = asyncio.create_task(workflow.execute())
    await asyncio.wait_for(terminal_evidence_entered.wait(), timeout=0.2)

    task.cancel("caller stopped during terminal evidence")
    release_terminal_evidence.set()
    with pytest.raises(WorkflowCancelledError, match="caller stopped during terminal evidence") as raised:
        await task

    cancellation = raised.value
    assert cancellation.state.status == "completed"
    assert cancellation.state_is_terminal is False
    assert isinstance(cancellation.__cause__, asyncio.CancelledError)
    assert cancellation.__cause__.args == ("caller stopped during terminal evidence",)
    assert isinstance(cancellation.terminalization_error, RuntimeError)
