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
