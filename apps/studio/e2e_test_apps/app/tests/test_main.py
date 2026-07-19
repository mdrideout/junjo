"""Regression tests for the live Studio E2E producer entry point."""

import asyncio
import sys
import threading
import unittest
from builtins import BaseExceptionGroup
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIRECTORY))

import main as producer  # noqa: E402


class FakeProvider:
    """Small provider double that records terminal lifecycle calls."""

    flush_result = True
    instances: list["FakeProvider"] = []

    def __init__(self, *, resource: object) -> None:
        self.resource = resource
        self.span_processors: list[object] = []
        self.force_flush_calls: list[int] = []
        self.shutdown_calls = 0
        self.instances.append(self)

    def add_span_processor(self, processor: object) -> None:
        self.span_processors.append(processor)

    def force_flush(self, timeout_millis: int) -> bool:
        self.force_flush_calls.append(timeout_millis)
        return self.flush_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeExporter:
    """OTLP exporter double that records its connection configuration."""

    instances: list["FakeExporter"] = []

    def __init__(self, **config: object) -> None:
        self.config = config
        self.instances.append(self)


class FakeSpanProcessor:
    """Batch processor double that records the exporter it owns."""

    instances: list["FakeSpanProcessor"] = []

    def __init__(self, exporter: object) -> None:
        self.exporter = exporter
        self.instances.append(self)


class FakeWorkflow:
    async def execute(self) -> SimpleNamespace:
        state = SimpleNamespace(model_dump_json=lambda: '{"count": 3}')
        return SimpleNamespace(state=state)


class FailingWorkflow:
    async def execute(self) -> None:
        raise RuntimeError("workflow failed")


class ProducerMainTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeProvider.instances.clear()
        FakeProvider.flush_result = True
        FakeExporter.instances.clear()
        FakeSpanProcessor.instances.clear()

    def run_main(self) -> int:
        config = {
            "exporter": {
                "host": "studio-ingestion",
                "port": 26155,
                "api_key": "test-key",
                "service_name": "configured-service",
                "insecure": True,
            },
            "app": {"num_workflows": 1},
        }
        with (
            patch.object(producer, "load_config", return_value=config),
            patch.object(producer, "TracerProvider", FakeProvider),
            patch.object(producer, "OTLPSpanExporter", FakeExporter),
            patch.object(producer, "BatchSpanProcessor", FakeSpanProcessor),
            patch.object(producer.trace, "set_tracer_provider"),
            patch.object(producer, "create_workflow", return_value=FakeWorkflow()),
        ):
            return producer.main(
                [
                    "--config",
                    "unused.yaml",
                    "--service-name",
                    "cli-service",
                    "--num-workflows",
                    "1",
                ]
            )

    def test_true_main_path_runs_and_owns_provider_lifecycle(self) -> None:
        self.assertEqual(self.run_main(), 0)

        exporter = FakeExporter.instances[0]
        provider = FakeProvider.instances[0]
        self.assertEqual(
            exporter.config,
            {
                "endpoint": "studio-ingestion:26155",
                "insecure": True,
                "headers": (("x-junjo-api-key", "test-key"),),
                "timeout": 120,
            },
        )
        processor = FakeSpanProcessor.instances[0]
        self.assertIs(processor.exporter, exporter)
        self.assertEqual(provider.span_processors, [processor])
        self.assertEqual(
            provider.force_flush_calls,
            [producer.LOCAL_DRAIN_BUDGET_MILLIS],
        )
        self.assertEqual(provider.shutdown_calls, 1)

    def test_flush_failure_fails_process_after_shutdown(self) -> None:
        FakeProvider.flush_result = False

        with self.assertRaisesRegex(
            RuntimeError, "Local telemetry queue drain did not complete"
        ):
            self.run_main()

        self.assertEqual(FakeProvider.instances[0].shutdown_calls, 1)

    def test_locked_runtime_starts_only_the_trace_export_worker(self) -> None:
        config = {
            "exporter": {
                "host": "127.0.0.1",
                "port": "1",
                "api_key": "unused-test-key",
                "service_name": "startup-smoke",
                "insecure": True,
            },
            "app": {"num_workflows": 1},
        }
        observed_workers: list[str] = []

        class InspectingWorkflow(FakeWorkflow):
            async def execute(self) -> SimpleNamespace:
                observed_workers.extend(
                    thread.name
                    for thread in threading.enumerate()
                    if thread.name.startswith("Otel")
                )
                return await super().execute()

        with (
            patch.object(producer, "load_config", return_value=config),
            patch.object(
                producer, "create_workflow", return_value=InspectingWorkflow()
            ),
        ):
            self.assertEqual(producer.main([]), 0)

        self.assertEqual(observed_workers, ["OtelBatchSpanRecordProcessor"])
        self.assertFalse(
            any(thread.name.startswith("Otel") for thread in threading.enumerate())
        )

    def test_workflow_failure_is_flushed_and_shutdown_before_exit(self) -> None:
        config = {
            "exporter": {
                "host": "studio-ingestion",
                "port": "26155",
                "api_key": "test-key",
                "service_name": "test-service",
                "insecure": True,
            },
            "app": {"num_workflows": 1},
        }
        with (
            patch.object(producer, "load_config", return_value=config),
            patch.object(producer, "TracerProvider", FakeProvider),
            patch.object(producer, "OTLPSpanExporter", FakeExporter),
            patch.object(producer, "BatchSpanProcessor", FakeSpanProcessor),
            patch.object(producer.trace, "set_tracer_provider"),
            patch.object(producer, "create_workflow", return_value=FailingWorkflow()),
        ):
            with self.assertRaises(BaseExceptionGroup) as raised:
                producer.main([])

        self.assertIsInstance(raised.exception.exceptions[0], RuntimeError)
        self.assertEqual(str(raised.exception.exceptions[0]), "workflow failed")

        provider = FakeProvider.instances[0]
        self.assertEqual(
            provider.force_flush_calls,
            [producer.LOCAL_DRAIN_BUDGET_MILLIS],
        )
        self.assertEqual(provider.shutdown_calls, 1)

    def test_failed_workflow_settles_siblings_before_telemetry_cleanup(self) -> None:
        events: list[str] = []
        config = {
            "exporter": {
                "host": "studio-ingestion",
                "port": "26155",
                "api_key": "test-key",
                "service_name": "test-service",
                "insecure": True,
            },
            "app": {"num_workflows": 2},
        }

        class RecordingProvider(FakeProvider):
            def force_flush(self, timeout_millis: int) -> bool:
                events.append("force-flush")
                return super().force_flush(timeout_millis)

            def shutdown(self) -> None:
                events.append("shutdown")
                super().shutdown()

        class FailingAfterYieldWorkflow:
            async def execute(self) -> None:
                events.append("failing-started")
                await asyncio.sleep(0)
                raise RuntimeError("workflow failed")

        class SlowWorkflow:
            async def execute(self) -> None:
                events.append("slow-started")
                try:
                    await asyncio.Event().wait()
                finally:
                    events.append("slow-settled")

        with (
            patch.object(producer, "load_config", return_value=config),
            patch.object(producer, "TracerProvider", RecordingProvider),
            patch.object(producer, "OTLPSpanExporter", FakeExporter),
            patch.object(producer, "BatchSpanProcessor", FakeSpanProcessor),
            patch.object(producer.trace, "set_tracer_provider"),
            patch.object(
                producer,
                "create_workflow",
                side_effect=[FailingAfterYieldWorkflow(), SlowWorkflow()],
            ),
        ):
            with self.assertRaises(BaseExceptionGroup):
                producer.main([])

        self.assertLess(events.index("slow-settled"), events.index("force-flush"))
        self.assertLess(events.index("force-flush"), events.index("shutdown"))


if __name__ == "__main__":
    unittest.main()
