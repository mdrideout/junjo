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


class DummyMetricReader:
    def __init__(self) -> None:
        self.shutdown_calls: list[float] = []
        self.force_flush_calls: list[float] = []

    def shutdown(self, timeout_millis: float = 30000, **kwargs) -> None:
        self.shutdown_calls.append(timeout_millis)

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        self.force_flush_calls.append(timeout_millis)
        return True


class FailingSpanProcessor:
    def shutdown(self) -> None:
        raise RuntimeError("span shutdown failed")

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        raise RuntimeError("span flush failed")


class FailingMetricReader:
    def shutdown(self, timeout_millis: float = 30000, **kwargs) -> None:
        raise RuntimeError("metric shutdown failed")

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        raise RuntimeError("metric flush failed")


class FalseReturningSpanProcessor:
    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int | None = None) -> bool:
        return False


class FalseReturningMetricReader:
    def shutdown(self, timeout_millis: float = 30000, **kwargs) -> None:
        return

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        return False


def test_shutdown_calls_span_processor_and_metric_reader_shutdown() -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key="test-key",
        insecure=True,
    )
    span_processor = DummySpanProcessor()
    metric_reader = DummyMetricReader()
    exporter._span_processor = span_processor
    exporter._metric_reader = metric_reader

    success = exporter.shutdown(timeout_millis=1234)

    assert success is True
    assert span_processor.shutdown_called is True
    assert metric_reader.shutdown_calls == [1234]
    assert span_processor.force_flush_calls == []
    assert metric_reader.force_flush_calls == []


def test_flush_calls_force_flush_without_shutdown() -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key="test-key",
        insecure=True,
    )
    span_processor = DummySpanProcessor()
    metric_reader = DummyMetricReader()
    exporter._span_processor = span_processor
    exporter._metric_reader = metric_reader

    success = exporter.flush(timeout_millis=4321)

    assert success is True
    assert span_processor.force_flush_calls == [4321]
    assert metric_reader.force_flush_calls == [4321]
    assert span_processor.shutdown_called is False
    assert metric_reader.shutdown_calls == []


def test_shutdown_logs_warnings_when_component_shutdown_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FailingSpanProcessor()
    exporter._metric_reader = FailingMetricReader()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.shutdown(timeout_millis=1234)

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert (
        "Failed to shut down the Junjo span processor for endpoint localhost:50051."
        in messages
    )
    assert (
        "Failed to shut down the Junjo metric reader for endpoint localhost:50051."
        in messages
    )
    assert all(getattr(record, "endpoint", None) == "localhost:50051" for record in caplog.records)


def test_flush_logs_warnings_when_components_do_not_flush_cleanly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FalseReturningSpanProcessor()
    exporter._metric_reader = FalseReturningMetricReader()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.flush(timeout_millis=4321)

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert (
        "Junjo span processor force_flush returned false for endpoint localhost:50051."
        in messages
    )
    assert (
        "Junjo metric reader force_flush returned false for endpoint localhost:50051."
        in messages
    )
    assert all(getattr(record, "endpoint", None) == "localhost:50051" for record in caplog.records)


def test_flush_logs_warnings_when_component_flush_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key="test-key",
        insecure=True,
    )
    exporter._span_processor = FailingSpanProcessor()
    exporter._metric_reader = FailingMetricReader()

    with caplog.at_level(logging.WARNING, logger="junjo.telemetry"):
        success = exporter.flush(timeout_millis=4321)

    assert success is False
    messages = [record.getMessage() for record in caplog.records]
    assert (
        "Failed to force-flush the Junjo span processor for endpoint localhost:50051."
        in messages
    )
    assert (
        "Failed to force-flush the Junjo metric reader for endpoint localhost:50051."
        in messages
    )
    assert all(getattr(record, "endpoint", None) == "localhost:50051" for record in caplog.records)
