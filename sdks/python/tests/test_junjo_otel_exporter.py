import logging

import pytest

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter


class DummySpanProcessor:
    def __init__(self) -> None:
        self.shutdown_called = False
        self.force_flush_calls: list[int | None] = []

    def shutdown(self) -> None:
        self.shutdown_called = True

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        self.force_flush_calls.append(timeout_millis)
        return True


class FailingSpanProcessor:
    def shutdown(self) -> None:
        raise RuntimeError("span shutdown failed")

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        raise RuntimeError("span flush failed")


class FalseReturningSpanProcessor:
    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        return False


def test_exporter_exposes_only_the_studio_trace_component() -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )

    try:
        assert exporter.span_processor is not None
        assert not hasattr(exporter, "metric_reader")
    finally:
        exporter.shutdown()


def test_shutdown_calls_span_processor_shutdown() -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )
    span_processor = DummySpanProcessor()
    exporter._span_processor = span_processor

    success = exporter.shutdown()

    assert success is True
    assert span_processor.shutdown_called is True
    assert span_processor.force_flush_calls == []


def test_flush_calls_force_flush_without_shutdown() -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )
    span_processor = DummySpanProcessor()
    exporter._span_processor = span_processor

    success = exporter.flush(timeout_millis=4321)

    assert success is True
    assert span_processor.force_flush_calls == [4321]
    assert span_processor.shutdown_called is False


def test_shutdown_logs_warnings_when_component_shutdown_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FailingSpanProcessor()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.shutdown()

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert "Failed to shut down the Junjo span processor for endpoint localhost:26155." in messages
    assert all(getattr(record, "endpoint", None) == "localhost:26155" for record in caplog.records)


def test_flush_logs_warning_when_span_processor_does_not_flush_cleanly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FalseReturningSpanProcessor()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.flush(timeout_millis=4321)

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert "Junjo span processor force_flush returned false for endpoint localhost:26155." in messages
    assert all(getattr(record, "endpoint", None) == "localhost:26155" for record in caplog.records)


def test_flush_logs_warnings_when_component_flush_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="26155",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FailingSpanProcessor()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.flush(timeout_millis=4321)

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert "Failed to force-flush the Junjo span processor for endpoint localhost:26155." in messages
    assert all(getattr(record, "endpoint", None) == "localhost:26155" for record in caplog.records)
