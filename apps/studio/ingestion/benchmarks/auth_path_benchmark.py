#!/usr/bin/env python3
"""Benchmark Studio's real OTLP -> ingestion -> backend authorization path.

Run through the backend's locked Python environment from ``apps/studio``:

    uv run --project backend python ingestion/benchmarks/auth_path_benchmark.py

The harness starts only the canonical backend and ingestion services with a
Compose overlay that constrains them to one shared vCPU and 800 MiB of combined
container memory. It creates a temporary Studio user and API key through the
real HTTP API, drives OTLP exports, optionally drives authenticated hot/cold
queries, deletes the warmed key, measures revocation, writes JSON, and removes
all containers, volumes, and temporary data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import grpc
import httpx
from opentelemetry.proto.collector.trace.v1 import (
    trace_service_pb2,
    trace_service_pb2_grpc,
)
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

DEFAULT_STUDIO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_ROOT = Path(os.environ.get("JUNJO_BENCHMARK_COMPOSE_ROOT", DEFAULT_STUDIO_ROOT)).resolve()
BASE_COMPOSE = STUDIO_ROOT / "compose.yaml"
BENCHMARK_COMPOSE = Path(__file__).with_name("compose.auth-benchmark.yaml")
PROJECT_NAME = "junjo-auth-benchmark"
SYNTHETIC_EMAIL = "auth-benchmark@example.com"
SYNTHETIC_PASSWORD = "benchmark-password-123"
REVOCATION_ACCEPTANCE_TOLERANCE_SECONDS = 1.0
WAL_MTIME_COMPARISON_TOLERANCE_MS = 2.0


@dataclass(frozen=True)
class BenchmarkConfig:
    implementation_label: str
    cache_ttl_seconds: int
    cache_max_entries: int
    validation_max_concurrency: int
    validation_max_pending: int
    validation_timeout_ms: int
    exporters: int
    exports_per_exporter: int
    spans_per_export: int
    query_workers: int
    export_interval_ms: int
    cadence_mode: str
    key_topology: str
    timing: str
    round_barrier: bool
    max_retries: int
    measure_revocation: bool
    wal_probe_spans: int
    use_auth_proxy: bool
    workload_auth_delay_ms: int
    run_failure_probes: bool
    restart_count: int


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile_value)
    return ordered[index]


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
    return {
        "mean_ms": statistics.fmean(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
    }


def retry_delay_seconds(exporter_id: int, attempt: int) -> float:
    """Return deterministic exporter-specific exponential backoff with jitter."""
    base_delay = min(0.05 * (2**attempt), 0.5)
    jitter_unit = ((exporter_id * 37 + attempt * 17) % 100) / 100
    return min(base_delay * (0.5 + jitter_unit), 0.75)


def require_free_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"benchmark requires free localhost port {port}") from error


def compose_command(use_auth_proxy: bool, *arguments: str) -> list[str]:
    command = [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
    ]
    if use_auth_proxy:
        command.extend(("--profile", "auth-proxy"))
    command.extend(
        [
            "--file",
            str(BASE_COMPOSE),
            "--file",
            str(BENCHMARK_COMPOSE),
            *arguments,
        ]
    )
    return command


def run(
    command: list[str], *, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=STUDIO_ROOT,
        env=env,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def benchmark_environment(
    config: BenchmarkConfig,
    data_path: Path,
    backend_port: int,
    ingestion_port: int,
    proxy_port: int,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "JUNJO_BUILD_TARGET": "production",
            "JUNJO_HOST_DB_DATA_PATH": str(data_path),
            "JUNJO_API_KEY_CACHE_TTL_SECONDS": str(config.cache_ttl_seconds),
            "JUNJO_API_KEY_CACHE_MAX_ENTRIES": str(config.cache_max_entries),
            "JUNJO_API_KEY_VALIDATION_MAX_CONCURRENCY": str(config.validation_max_concurrency),
            "JUNJO_API_KEY_VALIDATION_MAX_PENDING": str(config.validation_max_pending),
            "JUNJO_API_KEY_VALIDATION_TIMEOUT_MS": str(config.validation_timeout_ms),
            "JUNJO_BENCHMARK_BACKEND_PORT": str(backend_port),
            "JUNJO_BENCHMARK_INGESTION_PORT": str(ingestion_port),
            "JUNJO_BENCHMARK_PROXY_PORT": str(proxy_port),
            "JUNJO_BENCHMARK_AUTH_HOST": ("auth-proxy" if config.use_auth_proxy else "backend"),
            "JUNJO_BENCHMARK_AUTH_PORT": ("50054" if config.use_auth_proxy else "50053"),
            "JUNJO_BENCHMARK_BACKEND_CPUS": ("0.45" if config.use_auth_proxy else "0.50"),
            "JUNJO_BENCHMARK_INGESTION_CPUS": ("0.45" if config.use_auth_proxy else "0.50"),
        }
    )
    return environment


async def wait_for_backend(client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = await client.get("/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.25)
    raise RuntimeError("Studio backend did not become ready")


async def wait_for_proxy(client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = await client.get("/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.1)
    raise RuntimeError("benchmark authorization proxy did not become ready")


async def create_api_keys(
    client: httpx.AsyncClient, key_count: int, *, name_prefix: str
) -> list[tuple[str, str]]:
    identities: list[tuple[str, str]] = []
    for key_index in range(key_count):
        response = await client.post(
            "/api_keys",
            json={"name": f"{name_prefix}-{key_index}"},
            timeout=15,
        )
        response.raise_for_status()
        document = response.json()
        identities.append((str(document["id"]), str(document["key"])))
    return identities


async def create_benchmark_identities(
    client: httpx.AsyncClient, key_count: int
) -> list[tuple[str, str]]:
    response = await client.post(
        "/users/create-first-user",
        json={"email": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD},
        timeout=15,
    )
    response.raise_for_status()
    return await create_api_keys(client, key_count, name_prefix="auth-benchmark")


def make_export_request(
    spans_per_export: int, exporter_id: int
) -> trace_service_pb2.ExportTraceServiceRequest:
    now_ns = time.time_ns()
    spans: list[trace_pb2.Span] = []
    for span_index in range(spans_per_export):
        identity = exporter_id.to_bytes(8, "big") + span_index.to_bytes(8, "big")
        spans.append(
            trace_pb2.Span(
                trace_id=identity,
                span_id=(exporter_id * 1_000_000 + span_index).to_bytes(8, "big"),
                name="junjo.auth.benchmark",
                kind=trace_pb2.Span.SPAN_KIND_INTERNAL,
                start_time_unix_nano=now_ns,
                end_time_unix_nano=now_ns + 1_000,
            )
        )
    return trace_service_pb2.ExportTraceServiceRequest(
        resource_spans=[
            trace_pb2.ResourceSpans(
                resource=resource_pb2.Resource(
                    attributes=[
                        common_pb2.KeyValue(
                            key="service.name",
                            value=common_pb2.AnyValue(string_value="auth-benchmark"),
                        )
                    ]
                ),
                scope_spans=[trace_pb2.ScopeSpans(spans=spans)],
            )
        ]
    )


async def export_once(
    stub: trace_service_pb2_grpc.TraceServiceStub,
    request: trace_service_pb2.ExportTraceServiceRequest,
    api_key: str,
    *,
    timeout_seconds: float = 10,
) -> tuple[str, float]:
    started = time.perf_counter()
    try:
        await stub.Export(
            request,
            metadata=(("x-junjo-api-key", api_key),),
            timeout=timeout_seconds,
        )
        return "OK", (time.perf_counter() - started) * 1000
    except grpc.aio.AioRpcError as error:
        return error.code().name, (time.perf_counter() - started) * 1000


async def export_worker(
    exporter_id: int,
    config: BenchmarkConfig,
    api_key: str,
    ingestion_target: str,
    start: asyncio.Event,
    latencies_ms: list[float],
    attempt_codes: Counter[str],
    final_codes: Counter[str],
    round_barrier: asyncio.Barrier | None,
) -> None:
    request = make_export_request(config.spans_per_export, exporter_id)
    async with grpc.aio.insecure_channel(ingestion_target) as channel:
        stub = trace_service_pb2_grpc.TraceServiceStub(channel)
        await start.wait()
        interval_seconds = config.export_interval_ms / 1000
        next_start = time.perf_counter()
        if config.timing == "staggered" and interval_seconds > 0:
            next_start += (exporter_id / config.exporters) * interval_seconds

        for export_index in range(config.exports_per_exporter):
            if config.cadence_mode == "start-to-start" and interval_seconds > 0:
                await asyncio.sleep(max(0, next_start - time.perf_counter()))
            elif config.cadence_mode == "after-completion" and interval_seconds > 0:
                if export_index > 0:
                    await asyncio.sleep(interval_seconds)
                elif config.timing == "staggered":
                    await asyncio.sleep((exporter_id / config.exporters) * interval_seconds)
            started = time.perf_counter()
            for attempt in range(config.max_retries + 1):
                try:
                    await stub.Export(
                        request,
                        metadata=(("x-junjo-api-key", api_key),),
                        timeout=10,
                    )
                    attempt_codes["OK"] += 1
                    final_codes["OK"] += 1
                    break
                except grpc.aio.AioRpcError as error:
                    code = error.code().name
                    attempt_codes[code] += 1
                    if error.code() != grpc.StatusCode.UNAVAILABLE or attempt == config.max_retries:
                        final_codes[code] += 1
                        break
                    await asyncio.sleep(retry_delay_seconds(exporter_id, attempt))
            latencies_ms.append((time.perf_counter() - started) * 1000)
            if round_barrier is not None and export_index + 1 < config.exports_per_exporter:
                await round_barrier.wait()
            if config.cadence_mode == "start-to-start":
                next_start += interval_seconds


async def query_worker(
    client: httpx.AsyncClient,
    stop: asyncio.Event,
    latencies_ms: list[float],
    result_codes: Counter[str],
) -> None:
    while not stop.is_set():
        started = time.perf_counter()
        try:
            response = await client.get("/api/v1/observability/services", timeout=10)
            result_codes[str(response.status_code)] += 1
        except httpx.HTTPError:
            result_codes["transport_error"] += 1
        latencies_ms.append((time.perf_counter() - started) * 1000)
        await asyncio.sleep(0.05)


def parse_memory_mib(value: str) -> float:
    match = re.fullmatch(r"([0-9.]+)\s*([KMGT]?i?B)", value.strip())
    if match is None:
        raise ValueError(f"unrecognized Docker memory value: {value!r}")
    number, unit = match.groups()
    scale = {
        "B": 1 / (1024 * 1024),
        "KB": 1000 / (1024 * 1024),
        "MB": 1_000_000 / (1024 * 1024),
        "GB": 1_000_000_000 / (1024 * 1024),
        "TB": 1_000_000_000_000 / (1024 * 1024),
        "KiB": 1 / 1024,
        "MiB": 1,
        "GiB": 1024,
        "TiB": 1024 * 1024,
    }[unit]
    return float(number) * scale


async def sample_resources(
    environment: dict[str, str],
    stop: asyncio.Event,
    samples: dict[str, list[dict[str, float]]],
    *,
    use_auth_proxy: bool,
) -> None:
    ids = {
        service: run(
            compose_command(use_auth_proxy, "ps", "--quiet", service),
            env=environment,
        ).stdout.strip()
        for service in ("backend", "ingestion")
    }
    while not stop.is_set():
        command = [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}",
            *ids.values(),
        ]
        result = await asyncio.to_thread(run, command, env=environment, check=False)
        for line in result.stdout.splitlines():
            name, cpu, memory, pids = line.split("|", 3)
            service = "backend" if "backend" in name else "ingestion"
            used_memory = memory.split("/", 1)[0].strip()
            process_result = await asyncio.to_thread(
                run,
                [
                    "docker",
                    "exec",
                    ids[service],
                    "sh",
                    "-c",
                    "fd=0; threads=0; self=$$; "
                    "for pid in $(cat /sys/fs/cgroup/cgroup.procs); do "
                    '[ "$pid" = "$self" ] && continue; '
                    "comm=$(cat /proc/$pid/comm 2>/dev/null || true); "
                    '[ "$pid" = 1 ] && [ "$comm" = tini ] && continue; '
                    "count=$(ls /proc/$pid/fd 2>/dev/null | wc -l); "
                    "count=${count:-0}; "
                    "fd=$((fd + count)); "
                    "count=$(awk '/^Threads:/ {print $2}' /proc/$pid/status "
                    "2>/dev/null); count=${count:-0}; "
                    "threads=$((threads + count)); done; "
                    "echo $fd; echo $threads; "
                    "awk 'FNR > 1 {count++; "
                    'if ($4 == "01") established++; '
                    'if ($4 == "06") time_wait++} '
                    "END {print count+0; print established+0; print time_wait+0}' "
                    "/proc/1/net/tcp /proc/1/net/tcp6",
                ],
                env=environment,
                check=False,
            )
            process_values = process_result.stdout.splitlines()
            file_descriptors, threads, tcp_sockets, established, time_wait = (
                (float(value) for value in process_values[-5:])
                if len(process_values) >= 5
                else (0.0, 0.0, 0.0, 0.0, 0.0)
            )
            samples[service].append(
                {
                    "cpu_percent": float(cpu.rstrip("%")),
                    "memory_mib": parse_memory_mib(used_memory),
                    "pids": float(pids),
                    "file_descriptors": file_descriptors,
                    "threads": threads,
                    "tcp_sockets": tcp_sockets,
                    "established_tcp_sockets": established,
                    "time_wait_tcp_sockets": time_wait,
                }
            )
        await asyncio.sleep(0.5)


async def measure_revocation(
    client: httpx.AsyncClient,
    api_key_id: str,
    api_key: str,
    ttl_seconds: int,
    ingestion_target: str,
) -> dict[str, float | int | str | None]:
    request = make_export_request(1, 999_999)
    async with grpc.aio.insecure_channel(ingestion_target) as channel:
        stub = trace_service_pb2_grpc.TraceServiceStub(channel)
        # Force the previous workload's positive entry to expire, then warm a
        # new fixed window immediately before deletion. This measures the
        # near-worst-case revocation delay rather than the remaining TTL.
        if ttl_seconds > 0:
            await asyncio.sleep(ttl_seconds + 0.1)
        await stub.Export(request, metadata=(("x-junjo-api-key", api_key),), timeout=10)
        deleted_at = time.perf_counter()
        response = await client.delete(f"/api_keys/{api_key_id}", timeout=15)
        response.raise_for_status()

        accepted_after_delete = 0
        last_accepted_seconds: float | None = None
        deadline = deleted_at + max(ttl_seconds, 1) + 5
        while time.perf_counter() < deadline:
            try:
                await stub.Export(
                    request,
                    metadata=(("x-junjo-api-key", api_key),),
                    timeout=10,
                )
                accepted_after_delete += 1
                last_accepted_seconds = time.perf_counter() - deleted_at
            except grpc.aio.AioRpcError as error:
                if error.code() == grpc.StatusCode.UNAUTHENTICATED:
                    rejected_at = time.perf_counter()
                    return {
                        "status": "rejected",
                        "accepted_exports_after_delete": accepted_after_delete,
                        "last_accepted_seconds": last_accepted_seconds,
                        "first_rejection_seconds": rejected_at - deleted_at,
                    }
                if error.code() != grpc.StatusCode.UNAVAILABLE:
                    raise
            await asyncio.sleep(0.05)
    return {
        "status": "not_rejected_before_deadline",
        "accepted_exports_after_delete": accepted_after_delete,
        "last_accepted_seconds": last_accepted_seconds,
        "first_rejection_seconds": time.perf_counter() - deleted_at,
    }


async def proxy_mode(
    client: httpx.AsyncClient, *, delay_ms: int = 0, unavailable: bool = False
) -> dict[str, Any]:
    response = await client.post(
        "/mode",
        params={"delay_ms": delay_ms, "unavailable": str(unavailable).lower()},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


async def proxy_stats(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/stats", timeout=5)
    response.raise_for_status()
    return response.json()


async def proxy_reset(client: httpx.AsyncClient) -> None:
    response = await client.post("/reset", timeout=5)
    response.raise_for_status()


def durable_file_state(data_path: Path) -> dict[Path, int]:
    spans_root = data_path / "spans"
    if not spans_root.exists():
        return {}
    return {
        path: path.stat().st_mtime_ns
        for path in spans_root.rglob("*")
        if path.is_file() and path.suffix in {".ipc", ".parquet"}
    }


async def measure_wal_durability(
    data_path: Path,
    api_key: str,
    ingestion_target: str,
    spans: int,
) -> dict[str, Any]:
    before = durable_file_state(data_path)
    request = make_export_request(spans, 888_888)
    started = time.perf_counter()
    started_wall_ns = time.time_ns()

    async def observe_durable_change() -> tuple[float | None, float | None]:
        deadline = time.perf_counter() + 10
        while time.perf_counter() < deadline:
            current = durable_file_state(data_path)
            changed_mtimes = [
                mtime_ns
                for path, mtime_ns in current.items()
                if path not in before or mtime_ns > before[path]
            ]
            if changed_mtimes:
                observed_ms = (time.perf_counter() - started) * 1000
                durable_mtime_ms = (max(changed_mtimes) - started_wall_ns) / 1_000_000
                return observed_ms, durable_mtime_ms
            await asyncio.sleep(0.001)
        return None, None

    watcher = asyncio.create_task(observe_durable_change())
    async with grpc.aio.insecure_channel(ingestion_target) as channel:
        stub = trace_service_pb2_grpc.TraceServiceStub(channel)
        code, acknowledgement_ms = await export_once(stub, request, api_key)
    durable_observed_ms, durable_mtime_ms = await watcher
    return {
        "spans": spans,
        "result_code": code,
        "acknowledgement_ms": acknowledgement_ms,
        "durable_observed_ms": durable_observed_ms,
        "durable_file_mtime_ms": durable_mtime_ms,
        "durable_before_acknowledgement": (
            durable_mtime_ms is not None
            and durable_mtime_ms <= acknowledgement_ms + WAL_MTIME_COMPARISON_TOLERANCE_MS
        ),
        "mtime_comparison_tolerance_ms": WAL_MTIME_COMPARISON_TOLERANCE_MS,
    }


async def run_failure_probes(
    config: BenchmarkConfig,
    environment: dict[str, str],
    client: httpx.AsyncClient,
    proxy_client: httpx.AsyncClient,
    ingestion_target: str,
) -> dict[str, Any]:
    await proxy_mode(proxy_client)
    await proxy_reset(proxy_client)
    probe_key_count = 4 + config.restart_count
    identities = await create_api_keys(
        client,
        probe_key_count,
        name_prefix="auth-failure-probe",
    )
    keys = [api_key for _, api_key in identities]
    request = make_export_request(1, 777_777)
    results: dict[str, Any] = {}

    async with grpc.aio.insecure_channel(ingestion_target) as channel:
        stub = trace_service_pb2_grpc.TraceServiceStub(channel)

        invalid_codes = []
        invalid_key = "junjo_benchmark_invalid_key_not_in_database"
        for _ in range(2):
            code, _latency = await export_once(stub, request, invalid_key)
            invalid_codes.append(code)
        invalid_stats = await proxy_stats(proxy_client)
        results["invalid_not_cached"] = {
            "result_codes": invalid_codes,
            "authoritative_requests": invalid_stats["requests"],
            "passed": invalid_codes == ["UNAUTHENTICATED", "UNAUTHENTICATED"]
            and invalid_stats["requests"] == 2,
        }

        await proxy_reset(proxy_client)
        below_timeout_delay_ms = max(1, config.validation_timeout_ms // 2)
        await proxy_mode(proxy_client, delay_ms=below_timeout_delay_ms)
        below_code, below_latency_ms = await export_once(stub, request, keys[0])
        above_timeout_delay_ms = config.validation_timeout_ms + 500
        await proxy_mode(proxy_client, delay_ms=above_timeout_delay_ms)
        timeout_code, timeout_latency_ms = await export_once(
            stub,
            request,
            keys[1],
            timeout_seconds=(config.validation_timeout_ms / 1000) + 5,
        )
        await proxy_mode(proxy_client)
        recovery_code, recovery_latency_ms = await export_once(stub, request, keys[1])
        results["delay_and_timeout"] = {
            "below_timeout_delay_ms": below_timeout_delay_ms,
            "below_timeout_result": below_code,
            "below_timeout_latency_ms": below_latency_ms,
            "above_timeout_delay_ms": above_timeout_delay_ms,
            "timeout_result": timeout_code,
            "timeout_latency_ms": timeout_latency_ms,
            "uncached_retry_result": recovery_code,
            "uncached_retry_latency_ms": recovery_latency_ms,
            "passed": below_code == "OK"
            and timeout_code == "UNAVAILABLE"
            and recovery_code == "OK",
        }

        if config.cache_ttl_seconds > 0:
            warm_code, _warm_latency = await export_once(stub, request, keys[2])
            await proxy_mode(proxy_client, unavailable=True)
            cached_outage_code, cached_outage_latency_ms = await export_once(stub, request, keys[2])
            await asyncio.sleep(config.cache_ttl_seconds + 0.1)
            expired_outage_code, expired_outage_latency_ms = await export_once(
                stub,
                request,
                keys[2],
                timeout_seconds=(config.validation_timeout_ms / 1000) + 5,
            )
            await proxy_mode(proxy_client)
            recovered_code, recovered_latency_ms = await export_once(stub, request, keys[2])
            results["outage"] = {
                "warm_result": warm_code,
                "cached_during_outage_result": cached_outage_code,
                "cached_during_outage_latency_ms": cached_outage_latency_ms,
                "expired_during_outage_result": expired_outage_code,
                "expired_during_outage_latency_ms": expired_outage_latency_ms,
                "recovered_result": recovered_code,
                "recovered_latency_ms": recovered_latency_ms,
                "passed": warm_code == "OK"
                and cached_outage_code == "OK"
                and expired_outage_code == "UNAVAILABLE"
                and recovered_code == "OK",
            }

        restart_recoveries: list[dict[str, Any]] = []
        for restart_index in range(config.restart_count):
            restart_started = time.perf_counter()
            restart = await asyncio.to_thread(
                run,
                compose_command(
                    True,
                    "restart",
                    "--timeout",
                    "2",
                    "auth-proxy",
                ),
                env=environment,
                check=False,
            )
            if restart.returncode != 0:
                restart_recoveries.append(
                    {
                        "restart": restart_index + 1,
                        "result": "compose_restart_failed",
                        "passed": False,
                    }
                )
                continue
            await wait_for_proxy(proxy_client)
            deadline = time.perf_counter() + 10
            attempts = 0
            result_code = "UNAVAILABLE"
            while time.perf_counter() < deadline:
                attempts += 1
                result_code, _latency = await export_once(
                    stub,
                    request,
                    keys[4 + restart_index],
                    timeout_seconds=(config.validation_timeout_ms / 1000) + 2,
                )
                if result_code == "OK":
                    break
                await asyncio.sleep(0.1)
            restart_recoveries.append(
                {
                    "restart": restart_index + 1,
                    "result": result_code,
                    "attempts": attempts,
                    "recovery_seconds": time.perf_counter() - restart_started,
                    "passed": result_code == "OK",
                }
            )

    results["restarts"] = {
        "runs": restart_recoveries,
        "passed": all(run_result["passed"] for run_result in restart_recoveries),
    }
    results["proxy_stats"] = await proxy_stats(proxy_client)
    results["passed"] = all(
        value["passed"] for key, value in results.items() if key not in {"proxy_stats", "passed"}
    )
    return results


async def execute_benchmark(
    config: BenchmarkConfig,
    environment: dict[str, str],
    backend_port: int,
    ingestion_port: int,
    proxy_port: int,
    data_path: Path,
) -> dict[str, Any]:
    ingestion_target = f"127.0.0.1:{ingestion_port}"
    async with (
        httpx.AsyncClient(base_url=f"http://127.0.0.1:{proxy_port}") as proxy_client,
        httpx.AsyncClient(base_url=f"http://127.0.0.1:{backend_port}") as client,
    ):
        await wait_for_backend(client)
        if config.use_auth_proxy:
            await wait_for_proxy(proxy_client)
            await proxy_mode(
                proxy_client,
                delay_ms=config.workload_auth_delay_ms,
            )
            await proxy_reset(proxy_client)
        key_count = 1 if config.key_topology == "shared" else config.exporters
        identities = await create_benchmark_identities(client, key_count)
        api_keys = [api_key for _, api_key in identities]

        export_latencies: list[float] = []
        export_attempt_codes: Counter[str] = Counter()
        export_final_codes: Counter[str] = Counter()
        query_latencies: list[float] = []
        query_codes: Counter[str] = Counter()
        resource_samples: dict[str, list[dict[str, float]]] = {
            "backend": [],
            "ingestion": [],
        }
        start = asyncio.Event()
        round_barrier = (
            asyncio.Barrier(config.exporters)
            if config.round_barrier and config.exporters > 1
            else None
        )
        query_stop = asyncio.Event()
        stats_stop = asyncio.Event()

        exporters = [
            asyncio.create_task(
                export_worker(
                    exporter_id,
                    config,
                    api_keys[0] if config.key_topology == "shared" else api_keys[exporter_id],
                    ingestion_target,
                    start,
                    export_latencies,
                    export_attempt_codes,
                    export_final_codes,
                    round_barrier,
                )
            )
            for exporter_id in range(config.exporters)
        ]
        query_tasks = [
            asyncio.create_task(query_worker(client, query_stop, query_latencies, query_codes))
            for _ in range(config.query_workers)
        ]
        stats_task = asyncio.create_task(
            sample_resources(
                environment,
                stats_stop,
                resource_samples,
                use_auth_proxy=config.use_auth_proxy,
            )
        )

        workload_started = time.perf_counter()
        start.set()
        await asyncio.gather(*exporters)
        workload_seconds = time.perf_counter() - workload_started
        query_stop.set()
        await asyncio.gather(*query_tasks)
        workload_authorization_stats = (
            await proxy_stats(proxy_client)
            if config.use_auth_proxy
            else {"status": "not_instrumented"}
        )
        post_workload_resources = {
            service: dict(samples[-1]) if samples else {}
            for service, samples in resource_samples.items()
        }

        wal_durability = (
            await measure_wal_durability(
                data_path,
                identities[0][1],
                ingestion_target,
                config.wal_probe_spans,
            )
            if config.wal_probe_spans > 0
            else {"status": "skipped"}
        )
        failure_probes = (
            await run_failure_probes(
                config,
                environment,
                client,
                proxy_client,
                ingestion_target,
            )
            if config.run_failure_probes
            else {"status": "skipped"}
        )
        revocation = (
            await measure_revocation(
                client,
                identities[0][0],
                identities[0][1],
                config.cache_ttl_seconds,
                ingestion_target,
            )
            if config.measure_revocation
            else {"status": "skipped"}
        )
        stats_stop.set()
        await stats_task

    total_exports = config.exporters * config.exports_per_exporter
    successful_exports = export_final_codes["OK"]
    successful_spans = successful_exports * config.spans_per_export
    resource_summary: dict[str, dict[str, float]] = {}
    for service, samples in resource_samples.items():
        resource_summary[service] = {
            "max_cpu_percent": max((sample["cpu_percent"] for sample in samples), default=0),
            "first_memory_mib": samples[0]["memory_mib"] if samples else 0,
            "last_memory_mib": samples[-1]["memory_mib"] if samples else 0,
            "max_memory_mib": max((sample["memory_mib"] for sample in samples), default=0),
            "max_pids": max((sample["pids"] for sample in samples), default=0),
            "first_file_descriptors": (samples[0]["file_descriptors"] if samples else 0),
            "last_file_descriptors": (samples[-1]["file_descriptors"] if samples else 0),
            "max_file_descriptors": max(
                (sample["file_descriptors"] for sample in samples), default=0
            ),
            "first_threads": samples[0]["threads"] if samples else 0,
            "last_threads": samples[-1]["threads"] if samples else 0,
            "max_threads": max((sample["threads"] for sample in samples), default=0),
            "first_tcp_sockets": samples[0]["tcp_sockets"] if samples else 0,
            "last_tcp_sockets": samples[-1]["tcp_sockets"] if samples else 0,
            "max_tcp_sockets": max((sample["tcp_sockets"] for sample in samples), default=0),
            "first_established_tcp_sockets": (
                samples[0]["established_tcp_sockets"] if samples else 0
            ),
            "last_established_tcp_sockets": (
                samples[-1]["established_tcp_sockets"] if samples else 0
            ),
            "max_established_tcp_sockets": max(
                (sample["established_tcp_sockets"] for sample in samples), default=0
            ),
            "first_time_wait_tcp_sockets": (samples[0]["time_wait_tcp_sockets"] if samples else 0),
            "last_time_wait_tcp_sockets": (samples[-1]["time_wait_tcp_sockets"] if samples else 0),
            "max_time_wait_tcp_sockets": max(
                (sample["time_wait_tcp_sockets"] for sample in samples), default=0
            ),
            "post_workload_memory_mib": post_workload_resources[service].get("memory_mib", 0),
            "post_workload_file_descriptors": post_workload_resources[service].get(
                "file_descriptors", 0
            ),
            "post_workload_threads": post_workload_resources[service].get("threads", 0),
            "post_workload_established_tcp_sockets": post_workload_resources[service].get(
                "established_tcp_sockets", 0
            ),
            "sample_count": len(samples),
        }

    acceptance = {
        "all_exports_succeeded": successful_exports == total_exports,
        "all_queries_succeeded": set(query_codes) <= {"200"},
    }
    if config.wal_probe_spans > 0:
        acceptance["wal_durable_before_acknowledgement"] = bool(
            wal_durability["durable_before_acknowledgement"]
        )
    if config.run_failure_probes:
        acceptance["failure_probes_passed"] = bool(failure_probes["passed"])
    if config.measure_revocation:
        last_accepted_seconds = revocation["last_accepted_seconds"]
        revocation_bound_met = last_accepted_seconds is None or (
            isinstance(last_accepted_seconds, float)
            and last_accepted_seconds
            <= config.cache_ttl_seconds + REVOCATION_ACCEPTANCE_TOLERANCE_SECONDS
        )
        acceptance["revocation_observed"] = revocation["status"] == "rejected"
        acceptance["revocation_acceptance_bound_met"] = revocation_bound_met

    return {
        "config": asdict(config),
        "constraints": {
            "backend_cpus": 0.45 if config.use_auth_proxy else 0.5,
            "backend_memory_mib": 450,
            "ingestion_cpus": 0.45 if config.use_auth_proxy else 0.5,
            "ingestion_memory_mib": 350,
            "instrumentation_proxy_cpus": 0.1 if config.use_auth_proxy else 0,
            "instrumentation_proxy_memory_mib": 64 if config.use_auth_proxy else 0,
        },
        "exports": {
            "requested": total_exports,
            "successful": successful_exports,
            "attempt_codes": dict(export_attempt_codes),
            "final_codes": dict(export_final_codes),
            "workload_seconds": workload_seconds,
            "exports_per_second": successful_exports / workload_seconds,
            "spans_per_second": successful_spans / workload_seconds,
            **latency_summary(export_latencies),
        },
        "queries": {
            "result_codes": dict(query_codes),
            **latency_summary(query_latencies),
        },
        "resources": resource_summary,
        "authorization_proxy": workload_authorization_stats,
        "wal_durability": wal_durability,
        "failure_probes": failure_probes,
        "revocation": revocation,
        "acceptance": acceptance,
        "acceptance_limits": {
            "revocation_acceptance_tolerance_seconds": (REVOCATION_ACCEPTANCE_TOLERANCE_SECONDS),
            "wal_mtime_comparison_tolerance_ms": WAL_MTIME_COMPARISON_TOLERANCE_MS,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation-label", default="bounded-current")
    parser.add_argument("--cache-ttl-seconds", type=int, default=10, choices=range(0, 601))
    parser.add_argument("--cache-max-entries", type=int, default=1024)
    parser.add_argument("--validation-max-concurrency", type=int, default=8)
    parser.add_argument("--validation-max-pending", type=int, default=32)
    parser.add_argument("--validation-timeout-ms", type=int, default=2000)
    parser.add_argument("--exporters", type=int, default=20)
    parser.add_argument("--exports-per-exporter", type=int, default=20)
    parser.add_argument("--spans-per-export", type=int, default=32)
    parser.add_argument("--query-workers", type=int, default=2)
    parser.add_argument("--export-interval-ms", type=int, default=5)
    parser.add_argument(
        "--cadence-mode",
        choices=("start-to-start", "after-completion"),
        default="start-to-start",
    )
    parser.add_argument("--key-topology", choices=("shared", "distinct"), default="shared")
    parser.add_argument("--timing", choices=("synchronized", "staggered"), default="synchronized")
    parser.add_argument(
        "--round-barrier",
        action="store_true",
        help="wait for all exporters between logical export rounds",
    )
    parser.add_argument("--max-retries", type=int, default=10)
    parser.add_argument(
        "--skip-revocation",
        action="store_true",
        help="skip the deletion-window probe for non-TTL parameter sweeps",
    )
    parser.add_argument(
        "--wal-probe-spans",
        type=int,
        default=1000,
        help="spans in the dedicated durable-WAL probe; zero disables it",
    )
    parser.add_argument(
        "--use-auth-proxy",
        action="store_true",
        help="route refreshes through the benchmark-only counting/fault proxy",
    )
    parser.add_argument(
        "--workload-auth-delay-ms",
        type=int,
        default=0,
        help="benchmark-proxy delay applied to authoritative workload refreshes",
    )
    parser.add_argument(
        "--run-failure-probes",
        action="store_true",
        help="probe invalid, delayed, timed-out, unavailable, and restarted auth",
    )
    parser.add_argument(
        "--restart-count",
        type=int,
        default=0,
        help="auth-proxy restarts performed by failure probes",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--backend-port", type=int, default=27154)
    parser.add_argument("--ingestion-port", type=int, default=27155)
    parser.add_argument("--proxy-port", type=int, default=27156)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BenchmarkConfig(
        implementation_label=args.implementation_label,
        cache_ttl_seconds=args.cache_ttl_seconds,
        cache_max_entries=args.cache_max_entries,
        validation_max_concurrency=args.validation_max_concurrency,
        validation_max_pending=args.validation_max_pending,
        validation_timeout_ms=args.validation_timeout_ms,
        exporters=args.exporters,
        exports_per_exporter=args.exports_per_exporter,
        spans_per_export=args.spans_per_export,
        query_workers=args.query_workers,
        export_interval_ms=args.export_interval_ms,
        cadence_mode=args.cadence_mode,
        key_topology=args.key_topology,
        timing=args.timing,
        round_barrier=args.round_barrier,
        max_retries=args.max_retries,
        measure_revocation=not args.skip_revocation,
        wal_probe_spans=args.wal_probe_spans,
        use_auth_proxy=args.use_auth_proxy,
        workload_auth_delay_ms=args.workload_auth_delay_ms,
        run_failure_probes=args.run_failure_probes,
        restart_count=args.restart_count,
    )
    if config.run_failure_probes and not config.use_auth_proxy:
        raise ValueError("--run-failure-probes requires --use-auth-proxy")
    if config.workload_auth_delay_ms > 0 and not config.use_auth_proxy:
        raise ValueError("--workload-auth-delay-ms requires --use-auth-proxy")
    if config.restart_count > 0 and not config.run_failure_probes:
        raise ValueError("--restart-count requires --run-failure-probes")
    if config.cache_ttl_seconds > 30 and config.implementation_label == "bounded-current":
        raise ValueError(
            "the active implementation rejects TTLs above 30 seconds; "
            "use an explicit historical implementation label only with a pinned baseline"
        )
    require_free_port(args.backend_port)
    require_free_port(args.ingestion_port)
    if config.use_auth_proxy:
        require_free_port(args.proxy_port)

    with tempfile.TemporaryDirectory(prefix="junjo-auth-benchmark-") as temporary_directory:
        data_path = Path(temporary_directory) / "data"
        data_path.mkdir()
        environment = benchmark_environment(
            config,
            data_path,
            args.backend_port,
            args.ingestion_port,
            args.proxy_port,
        )
        up_arguments = ["up", "--detach", "--wait", "--wait-timeout", "180"]
        if not args.skip_build:
            up_arguments.append("--build")
        up_arguments.extend(["backend", "ingestion"])
        if config.use_auth_proxy:
            up_arguments.append("auth-proxy")

        try:
            run(
                compose_command(config.use_auth_proxy, "config", "--quiet"),
                env=environment,
            )
            startup = run(
                compose_command(config.use_auth_proxy, *up_arguments),
                env=environment,
                check=False,
            )
            if startup.returncode != 0:
                raise RuntimeError(f"benchmark composition failed to start:\n{startup.stdout}")
            result = asyncio.run(
                execute_benchmark(
                    config,
                    environment,
                    args.backend_port,
                    args.ingestion_port,
                    args.proxy_port,
                    data_path,
                )
            )
        finally:
            run(
                compose_command(
                    config.use_auth_proxy,
                    "down",
                    "--volumes",
                    "--remove-orphans",
                    "--timeout",
                    "10",
                ),
                env=environment,
                check=False,
            )

    result["recorded_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if all(result["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
