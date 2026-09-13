"""Measure Store updates and complete workflows in a fresh process per case.

Select a checkout with PYTHONPATH=<checkout>/sdks/python/src. Run baseline and
candidate with the same interpreter, dependencies, arguments and container limits.
"""

import argparse
import asyncio
import gc
import hashlib
import inspect
import json
import resource
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from junjo import BaseState, BaseStore, Edge, Graph, Node, Workflow


class Payload(BaseModel):
    values: list[int]


class State(BaseState):
    count: int = 0
    payload: Payload


class Store(BaseStore[State]):
    async def set_count(self, count: int) -> None:
        await self.set_state({"count": count})


class Increment(Node[Store]):
    async def service(self, store: Store) -> None:
        snapshot = await store.get_state()
        await store.set_count(snapshot.count + 1)


def resident_mib() -> float | None:
    status = Path("/proc/self/status")
    if not status.exists():
        return None
    for line in status.read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return None


async def measure(case: str, iterations: int, size: int, warmup_iterations: int) -> dict:
    store = Store(State(payload=Payload(values=list(range(size)))))
    payloads = [Payload(values=list(range(size))), Payload(values=list(range(1, size + 1)))]
    nodes = [Increment() for _ in range(8)]
    workflow = Workflow[State, Store](
        graph_factory=lambda nodes=nodes: Graph(
            source=nodes[0],
            sinks=[nodes[-1]],
            edges=[Edge(tail=tail, head=head) for tail, head in zip(nodes, nodes[1:], strict=False)],
        ),
        store_factory=lambda: Store(State(payload=Payload(values=list(range(size))))),
    )
    before_memory = resident_mib()
    durations = []
    cpu_start = time.process_time()
    started = time.perf_counter()
    for index in range(-warmup_iterations, iterations):
        if index == 0:
            before_memory = resident_mib()
            cpu_start = time.process_time()
            started = time.perf_counter()
        operation_started = time.perf_counter()
        if case == "workflow":
            result = await workflow.execute()
            assert result.state.count == len(nodes)
        elif case == "replace":
            await store.set_state({"payload": payloads[index % 2]})
        elif case == "noop":
            await store.set_state({"payload": payloads[0]})
        elif case == "prospective":
            await store._validate_state_update({"payload": payloads[index % 2]})
        else:
            await store.set_count(index + 1)
        if index >= 0:
            durations.append((time.perf_counter() - operation_started) * 1000)
    elapsed = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_start
    evidence = await store._get_store_owner_evidence()
    assert evidence.reconstructable
    if case == "scalar":
        assert (await store.get_state()).count == iterations
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mib = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
    after_memory = resident_mib()
    del store, payloads, workflow, nodes
    gc.collect()
    ordered = sorted(durations)
    return {
        "completed": iterations,
        "wall_seconds": elapsed,
        "operations_per_second": iterations / elapsed,
        "cpu_seconds": cpu_seconds,
        "cpu_us_per_operation": cpu_seconds * 1_000_000 / iterations,
        "p95_ms": ordered[round((len(ordered) - 1) * 0.95)],
        "p99_ms": ordered[round((len(ordered) - 1) * 0.99)],
        "peak_rss_mib": peak_mib,
        "before_rss_mib": before_memory,
        "after_work_rss_mib": after_memory,
        "after_release_rss_mib": resident_mib(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["scalar", "replace", "noop", "prospective", "workflow"], required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--warmup-iterations", type=int, default=0)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(measure(args.case, args.iterations, args.size, args.warmup_iterations))
    source = Path(inspect.getfile(BaseStore))
    result.update(
        {
            "label": args.label,
            "case": args.case,
            "iterations": args.iterations,
            "warmup_iterations": args.warmup_iterations,
            "size": args.size,
            "python": sys.version,
            "store_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
