"""Use the existing delivery/resource harness with real Agent trace-evidence queries.

JUNJO_STORE_BENCHMARK_FIXTURE selects an unchanged or shared-Store contract fixture.
The warmup trace is excluded from offered-work/delivery counts in both variants.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "apps/studio/ingestion/benchmarks"))
import auth_path_benchmark as harness
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

FIXTURE = json.loads(Path(os.environ["JUNJO_STORE_BENCHMARK_FIXTURE"]).read_text())
SEED_TRACE = bytes.fromhex("ab" * 16)
SEED_URL = f"/api/v1/trace-evidence/{SEED_TRACE.hex()}"


def attributes(values):
    def value(item):
        if isinstance(item, bool):
            return common_pb2.AnyValue(bool_value=item)
        if isinstance(item, int):
            return common_pb2.AnyValue(int_value=item)
        if isinstance(item, float):
            return common_pb2.AnyValue(double_value=item)
        if isinstance(item, list):
            return common_pb2.AnyValue(array_value=common_pb2.ArrayValue(values=[value(x) for x in item]))
        return common_pb2.AnyValue(string_value=item)
    return [common_pb2.KeyValue(key=key, value=value(item)) for key, item in values.items()]


def make_request(count, exporter_id):
    assert count == len(FIXTURE["spans"])
    source = FIXTURE["spans"]
    ids = {item["span_id"]: (index + 1).to_bytes(8, "big") for index, item in enumerate(source)}
    origin = datetime.fromisoformat(source[0]["start_time"]).timestamp()
    now = time.time_ns()
    def timestamp(text):
        return now + round((datetime.fromisoformat(text).timestamp() - origin) * 1_000_000_000)
    spans = []
    for item in source:
        spans.append(trace_pb2.Span(
            trace_id=SEED_TRACE, span_id=ids[item["span_id"]],
            parent_span_id=ids.get(item["parent_span_id"], b""), name=item["name"],
            kind=trace_pb2.Span.SPAN_KIND_INTERNAL,
            start_time_unix_nano=timestamp(item["start_time"]), end_time_unix_nano=timestamp(item["end_time"]),
            attributes=attributes(item["attributes_json"]),
            events=[trace_pb2.Span.Event(name=event["name"],
                    time_unix_nano=now + int(event["timeUnixNano"]) - round(origin * 1_000_000_000),
                    attributes=attributes(event["attributes"])) for event in item["events_json"]],
            status=trace_pb2.Status(code=int(item["status_code"])), flags=item["trace_flags"],
        ))
    return harness.trace_service_pb2.ExportTraceServiceRequest(resource_spans=[trace_pb2.ResourceSpans(
        resource=resource_pb2.Resource(attributes=attributes(source[0]["resource_attributes_json"])),
        scope_spans=[trace_pb2.ScopeSpans(spans=spans)],
    )])


create_identities = harness.create_benchmark_identities


async def create_and_warm(client, count):
    identities = await create_identities(client, count)
    async with harness.grpc.aio.insecure_channel("127.0.0.1:27155") as channel:
        stub = harness.trace_service_pb2_grpc.TraceServiceStub(channel)
        code, _ = await harness.export_once(stub, make_request(len(FIXTURE["spans"]), 0), identities[0][1])
        assert code == "OK", code
    while True:
        response = await client.get(SEED_URL)
        if response.status_code != 404:
            response.raise_for_status()
            evidence = response.json()
            assert not evidence["diagnostics"], evidence["diagnostics"]
            output = os.environ.get("JUNJO_STORE_BENCHMARK_EVIDENCE")
            if output:
                Path(output).write_text(json.dumps(evidence, indent=2) + "\n")
            break
        await asyncio.sleep(0.05)
    return identities


async def query_evidence(client, stop, latencies, codes):
    while not stop.is_set():
        started = time.perf_counter()
        response = await client.get(SEED_URL)
        codes[str(response.status_code)] += 1
        if response.status_code == 200:
            assert not response.json()["diagnostics"]
        latencies.append((time.perf_counter() - started) * 1000)
        await asyncio.sleep(0.05)


harness.make_export_request = make_request
harness.create_benchmark_identities = create_and_warm
harness.query_worker = query_evidence
raise SystemExit(harness.main())
