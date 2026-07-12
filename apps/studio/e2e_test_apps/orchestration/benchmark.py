"""
Pure throughput benchmark for the ingestion service.

This bypasses workflow execution overhead and measures raw span ingestion throughput.
Use this to benchmark the Rust ingestion service independently of Python/workflow overhead.

Usage:
    uv run python benchmark.py --spans 100000 --batch-size 1000 --concurrency 10
"""

import argparse
import asyncio
import os
import time
from dataclasses import dataclass

# Configure OTEL for maximum throughput BEFORE imports
os.environ["OTEL_BSP_SCHEDULE_DELAY"] = "50"  # 50ms - very aggressive
os.environ["OTEL_BSP_MAX_EXPORT_BATCH_SIZE"] = "4096"
os.environ["OTEL_BSP_MAX_QUEUE_SIZE"] = "16384"
os.environ["OTEL_BSP_EXPORT_TIMEOUT"] = "30000"

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

import yaml


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark."""
    total_spans: int
    batch_size: int
    concurrency: int
    host: str
    port: str
    api_key: str
    insecure: bool = True


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""
    total_spans: int
    duration_seconds: float
    spans_per_second: float
    batches_sent: int
    flush_duration_seconds: float


def load_config(config_path: str) -> dict:
    """Load YAML configuration file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


async def generate_spans_batch(
    tracer: trace.Tracer,
    batch_id: int,
    spans_per_batch: int,
    service_name: str,
) -> int:
    """
    Generate a batch of spans as fast as possible.

    Each span is minimal - just enough to be valid OTLP.
    """
    spans_created = 0

    for i in range(spans_per_batch):
        with tracer.start_as_current_span(
            f"benchmark-span-{batch_id}-{i}",
            attributes={
                "benchmark.batch_id": batch_id,
                "benchmark.span_index": i,
                "benchmark.service": service_name,
            }
        ) as span:
            # Minimal work - just set a few attributes
            span.set_attribute("benchmark.timestamp", time.time_ns())
            spans_created += 1

    return spans_created


async def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    """
    Run the throughput benchmark.

    Strategy:
    1. Set up OTEL with aggressive batching
    2. Spawn concurrent tasks that generate spans as fast as possible
    3. Wait for all tasks to complete
    4. Force flush and measure total time
    """
    # Setup OTEL
    resource = Resource.create({"service.name": "benchmark-service"})
    provider = TracerProvider(resource=resource)

    endpoint = f"{config.host}:{config.port}"
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=config.insecure,
        headers=[("x-junjo-api-key", config.api_key)],
    )

    # Use BatchSpanProcessor with aggressive settings
    processor = BatchSpanProcessor(
        exporter,
        max_queue_size=16384,
        max_export_batch_size=4096,
        schedule_delay_millis=50,
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("benchmark")

    # Calculate work distribution
    spans_per_batch = config.batch_size
    total_batches = (config.total_spans + spans_per_batch - 1) // spans_per_batch
    batches_per_worker = (total_batches + config.concurrency - 1) // config.concurrency

    print(f"\nBenchmark Configuration:")
    print(f"  Target spans: {config.total_spans:,}")
    print(f"  Batch size: {spans_per_batch:,}")
    print(f"  Total batches: {total_batches:,}")
    print(f"  Concurrency: {config.concurrency}")
    print(f"  Batches per worker: {batches_per_worker}")
    print(f"  Endpoint: {endpoint}")
    print()

    # Generate spans
    print("Generating spans...")
    start_time = time.time()

    async def worker(worker_id: int) -> int:
        """Worker that generates multiple batches."""
        total_created = 0
        for batch_idx in range(batches_per_worker):
            batch_id = worker_id * batches_per_worker + batch_idx
            if batch_id >= total_batches:
                break

            # Calculate actual spans for this batch (last batch may be smaller)
            remaining = config.total_spans - (batch_id * spans_per_batch)
            actual_batch_size = min(spans_per_batch, remaining)
            if actual_batch_size <= 0:
                break

            created = await generate_spans_batch(
                tracer,
                batch_id,
                actual_batch_size,
                f"benchmark-worker-{worker_id}",
            )
            total_created += created
        return total_created

    # Run all workers concurrently
    tasks = [worker(i) for i in range(config.concurrency)]
    results = await asyncio.gather(*tasks)

    generation_time = time.time() - start_time
    total_created = sum(results)

    print(f"Generated {total_created:,} spans in {generation_time:.2f}s")
    print(f"  Generation rate: {total_created / generation_time:,.0f} spans/sec")
    print()

    # Force flush to ensure all spans are sent
    print("Flushing spans to server...")
    flush_start = time.time()
    provider.force_flush(timeout_millis=60000)  # 60 second timeout
    flush_duration = time.time() - flush_start

    total_duration = time.time() - start_time

    # Shutdown
    provider.shutdown()

    return BenchmarkResult(
        total_spans=total_created,
        duration_seconds=total_duration,
        spans_per_second=total_created / total_duration,
        batches_sent=total_batches,
        flush_duration_seconds=flush_duration,
    )


def print_results(result: BenchmarkResult):
    """Print benchmark results."""
    print()
    print("=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Total spans sent:     {result.total_spans:,}")
    print(f"  Total duration:       {result.duration_seconds:.2f}s")
    print(f"  Flush duration:       {result.flush_duration_seconds:.2f}s")
    print(f"  Batches sent:         {result.batches_sent:,}")
    print()
    print(f"  📊 THROUGHPUT:        {result.spans_per_second:,.0f} spans/sec")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark the ingestion service throughput",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test (10K spans)
  uv run python benchmark.py --spans 10000

  # Medium test (100K spans)
  uv run python benchmark.py --spans 100000 --concurrency 20

  # Stress test (1M spans)
  uv run python benchmark.py --spans 1000000 --batch-size 2000 --concurrency 50
        """,
    )
    parser.add_argument(
        "--spans",
        type=int,
        default=100000,
        help="Total number of spans to generate (default: 100000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of spans per batch/task (default: 1000)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent workers (default: 10)",
    )
    parser.add_argument(
        "--config",
        default="../app/config.yaml",
        help="Path to config file for connection settings (default: ../app/config.yaml)",
    )
    args = parser.parse_args()

    # Load connection config from app config
    app_config = load_config(args.config)

    config = BenchmarkConfig(
        total_spans=args.spans,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        host=app_config["exporter"]["host"],
        port=app_config["exporter"]["port"],
        api_key=app_config["exporter"]["api_key"],
        insecure=app_config["exporter"].get("insecure", True),
    )

    print("🚀 Starting Ingestion Service Benchmark")
    print("=" * 60)

    result = asyncio.run(run_benchmark(config))
    print_results(result)


if __name__ == "__main__":
    main()
