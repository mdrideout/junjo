import builtins
import logging

import pytest

from junjo import (
    BaseState,
    BaseStore,
    Graph,
    Node,
    RunConcurrent,
    Workflow,
    WorkflowExecutionError,
)


class LoggingState(BaseState):
    status: str = "pending"


class LoggingStore(BaseStore[LoggingState]):
    async def set_status(self, status: str) -> None:
        await self.set_state({"status": status})


class CompleteNode(Node[LoggingStore]):
    async def service(self, store: LoggingStore) -> None:
        await store.set_status("complete")


class FailingNode(Node[LoggingStore]):
    async def service(self, store: LoggingStore) -> None:
        raise RuntimeError("boom")


class NoopNode(Node[LoggingStore]):
    async def service(self, store: LoggingStore) -> None:
        return


def _unexpected_print(*args, **kwargs) -> None:
    raise AssertionError("core library runtime should not call print()")


def _create_single_node_graph(node: Node[LoggingStore]) -> Graph:
    return Graph(source=node, sinks=[node], edges=[])


def test_junjo_root_logger_uses_null_handler() -> None:
    root_logger = logging.getLogger("junjo")

    assert any(
        isinstance(handler, logging.NullHandler)
        for handler in root_logger.handlers
    )


@pytest.mark.asyncio
async def test_workflow_execution_logs_debug_without_print(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", _unexpected_print)
    workflow = Workflow[LoggingState, LoggingStore](
        name="Logging Workflow",
        graph_factory=lambda: _create_single_node_graph(CompleteNode()),
        store_factory=lambda: LoggingStore(initial_state=LoggingState()),
    )

    with caplog.at_level(logging.DEBUG, logger="junjo"):
        result = await workflow.execute()

    junjo_records = [record for record in caplog.records if record.name.startswith("junjo")]
    messages = [record.getMessage() for record in junjo_records]

    assert "Executing workflow Logging Workflow" in messages[0]
    assert any("Starting node CompleteNode" in message for message in messages)
    assert any("Completed node CompleteNode" in message for message in messages)
    assert any("Reached declared sink CompleteNode" in message for message in messages)
    assert any("Completed workflow Logging Workflow" in message for message in messages)
    assert all(getattr(record, "run_id", None) == result.run_id for record in junjo_records)


@pytest.mark.asyncio
async def test_node_failure_logs_exception_without_print(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = Workflow[LoggingState, LoggingStore](
        name="Failing Workflow",
        graph_factory=lambda: _create_single_node_graph(FailingNode()),
        store_factory=lambda: LoggingStore(initial_state=LoggingState()),
    )

    with caplog.at_level(logging.ERROR, logger="junjo"):
        with pytest.raises(WorkflowExecutionError) as raised:
            await workflow.execute()
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "boom"

    junjo_error_records = [
        record
        for record in caplog.records
        if record.name.startswith("junjo") and record.levelno >= logging.ERROR
    ]
    messages = [record.getMessage() for record in junjo_error_records]

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
    assert len(junjo_error_records) == 1
    assert "Workflow execution failed for Failing Workflow" in messages[0]
    assert getattr(junjo_error_records[0], "run_id", None) is not None


@pytest.mark.asyncio
async def test_run_concurrent_failure_emits_one_error_log_at_workflow_boundary(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def create_graph() -> Graph:
        run_concurrent = RunConcurrent(
            name="Parallel Work",
            items=[FailingNode(), NoopNode()],
        )
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[LoggingState, LoggingStore](
        name="Concurrent Failure Workflow",
        graph_factory=create_graph,
        store_factory=lambda: LoggingStore(initial_state=LoggingState()),
    )

    with caplog.at_level(logging.ERROR, logger="junjo"):
        with pytest.raises(WorkflowExecutionError) as raised:
            await workflow.execute()
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "boom"

    junjo_error_records = [
        record
        for record in caplog.records
        if record.name.startswith("junjo") and record.levelno >= logging.ERROR
    ]
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
    assert len(junjo_error_records) == 1
    assert "Workflow execution failed for Concurrent Failure Workflow" in (
        junjo_error_records[0].getMessage()
    )
    assert getattr(junjo_error_records[0], "run_id", None) is not None


@pytest.mark.asyncio
async def test_run_concurrent_logs_debug_without_print(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", _unexpected_print)

    def create_graph() -> Graph:
        run_concurrent = RunConcurrent(
            name="Parallel Work",
            items=[NoopNode(), NoopNode()],
        )
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[LoggingState, LoggingStore](
        name="Concurrent Workflow",
        graph_factory=create_graph,
        store_factory=lambda: LoggingStore(initial_state=LoggingState()),
    )

    with caplog.at_level(logging.DEBUG, logger="junjo"):
        result = await workflow.execute()

    junjo_records = [record for record in caplog.records if record.name.startswith("junjo")]
    messages = [record.getMessage() for record in junjo_records]

    assert any(
        "Executing concurrent items within Parallel Work" in message
        for message in messages
    )
    assert any(
        "Finished concurrent items within Parallel Work" in message
        for message in messages
    )
    assert any("Starting node NoopNode" in message for message in messages)
    assert all(getattr(record, "run_id", None) == result.run_id for record in junjo_records)
