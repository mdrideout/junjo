import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

from junjo_coding_agents.runtime import Runtime

provider = TracerProvider(sampler=ParentBased(ALWAYS_ON))
span_exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(span_exporter))
trace.set_tracer_provider(provider)


@pytest.fixture
def exporter():
    span_exporter.clear()
    return span_exporter


@pytest.fixture
async def runtime(exporter):
    instance = Runtime(provider.get_tracer("proof"))
    yield instance
    await instance.shutdown()
