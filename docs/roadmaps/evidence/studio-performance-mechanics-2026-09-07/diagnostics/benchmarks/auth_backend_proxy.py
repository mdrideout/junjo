#!/usr/bin/env python3
"""Benchmark-only controllable proxy for Studio's internal auth gRPC service."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import grpc

from app.proto_gen import auth_pb2, auth_pb2_grpc


@dataclass
class ProxyStats:
    requests: int = 0
    valid: int = 0
    invalid: int = 0
    unavailable: int = 0
    active: int = 0
    max_active: int = 0
    latency_micros_total: int = 0
    latency_micros_max: int = 0


class ProxyState:
    def __init__(self) -> None:
        self.delay_ms = 0
        self.force_unavailable = False
        self.stats = ProxyStats()
        self.lock = asyncio.Lock()

    async def start_request(self) -> None:
        async with self.lock:
            self.stats.requests += 1
            self.stats.active += 1
            self.stats.max_active = max(self.stats.max_active, self.stats.active)

    async def finish_request(
        self, *, valid: bool | None, unavailable: bool, elapsed_micros: int
    ) -> None:
        async with self.lock:
            self.stats.active -= 1
            if unavailable:
                self.stats.unavailable += 1
            elif valid:
                self.stats.valid += 1
            else:
                self.stats.invalid += 1
            self.stats.latency_micros_total += elapsed_micros
            self.stats.latency_micros_max = max(self.stats.latency_micros_max, elapsed_micros)

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            document = asdict(self.stats)
            requests = self.stats.requests
            document["latency_micros_mean"] = (
                self.stats.latency_micros_total / requests if requests else 0
            )
            document["delay_ms"] = self.delay_ms
            document["force_unavailable"] = self.force_unavailable
            return document

    async def reset(self) -> None:
        async with self.lock:
            active = self.stats.active
            self.stats = ProxyStats(active=active, max_active=active)

    async def set_mode(self, *, delay_ms: int, force_unavailable: bool) -> None:
        async with self.lock:
            self.delay_ms = delay_ms
            self.force_unavailable = force_unavailable


class AuthProxy(auth_pb2_grpc.InternalAuthServiceServicer):
    def __init__(self, state: ProxyState, backend_target: str) -> None:
        self.state = state
        self.channel = grpc.aio.insecure_channel(backend_target)
        self.stub = auth_pb2_grpc.InternalAuthServiceStub(self.channel)

    async def close(self) -> None:
        await self.channel.close()

    async def ValidateApiKey(  # noqa: N802 - generated gRPC method name
        self,
        request: auth_pb2.ValidateApiKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ValidateApiKeyResponse:
        started = time.perf_counter_ns()
        await self.state.start_request()
        valid: bool | None = None
        unavailable = False
        try:
            async with self.state.lock:
                delay_ms = self.state.delay_ms
                force_unavailable = self.state.force_unavailable
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if force_unavailable:
                unavailable = True
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE,
                    "benchmark auth proxy forced unavailable",
                )

            supplied_token = dict(context.invocation_metadata()).get("x-junjo-internal-token", "")
            try:
                response = await self.stub.ValidateApiKey(
                    request,
                    metadata=(("x-junjo-internal-token", supplied_token),),
                )
            except asyncio.CancelledError:
                unavailable = True
                raise
            except grpc.aio.AioRpcError as error:
                unavailable = error.code() == grpc.StatusCode.UNAVAILABLE
                await context.abort(error.code(), error.details())
                raise RuntimeError("gRPC context.abort returned unexpectedly")
            valid = bool(response.is_valid)
            return response
        except asyncio.CancelledError:
            unavailable = True
            raise
        finally:
            elapsed_micros = (time.perf_counter_ns() - started) // 1000
            await self.state.finish_request(
                valid=valid,
                unavailable=unavailable,
                elapsed_micros=elapsed_micros,
            )


def json_response(status: str, document: dict[str, Any]) -> bytes:
    body = json.dumps(document, sort_keys=True).encode()
    return (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode() + body


async def handle_control(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: ProxyState,
) -> None:
    try:
        header = await reader.readuntil(b"\r\n\r\n")
        request_line = header.split(b"\r\n", 1)[0].decode()
        method, raw_target, _version = request_line.split(" ", 2)
        target = urlsplit(raw_target)
        query = parse_qs(target.query)

        if method == "GET" and target.path == "/health":
            response = json_response("200 OK", {"status": "ok"})
        elif method == "GET" and target.path == "/stats":
            response = json_response("200 OK", await state.snapshot())
        elif method == "POST" and target.path == "/reset":
            await state.reset()
            response = json_response("200 OK", await state.snapshot())
        elif method == "POST" and target.path == "/mode":
            delay_ms = int(query.get("delay_ms", ["0"])[0])
            if not 0 <= delay_ms <= 60_000:
                raise ValueError("delay_ms must be between 0 and 60000")
            unavailable = query.get("unavailable", ["false"])[0].lower() == "true"
            await state.set_mode(
                delay_ms=delay_ms,
                force_unavailable=unavailable,
            )
            response = json_response("200 OK", await state.snapshot())
        else:
            response = json_response("404 Not Found", {"error": "not found"})
    except (asyncio.IncompleteReadError, UnicodeDecodeError, ValueError) as error:
        response = json_response("400 Bad Request", {"error": str(error)})

    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main() -> None:
    grpc_port = int(os.environ.get("JUNJO_BENCHMARK_PROXY_GRPC_PORT", "50054"))
    control_port = int(os.environ.get("JUNJO_BENCHMARK_PROXY_CONTROL_PORT", "50055"))
    backend_target = os.environ.get("JUNJO_BENCHMARK_PROXY_BACKEND_TARGET", "backend:50053")

    state = ProxyState()
    proxy = AuthProxy(state, backend_target)
    server = grpc.aio.server()
    auth_pb2_grpc.add_InternalAuthServiceServicer_to_server(proxy, server)
    server.add_insecure_port(f"0.0.0.0:{grpc_port}")
    await server.start()

    control = await asyncio.start_server(
        lambda reader, writer: handle_control(reader, writer, state),
        "0.0.0.0",
        control_port,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop.set)

    await stop.wait()
    control.close()
    await control.wait_closed()
    await server.stop(grace=2)
    await proxy.close()


if __name__ == "__main__":
    asyncio.run(main())
