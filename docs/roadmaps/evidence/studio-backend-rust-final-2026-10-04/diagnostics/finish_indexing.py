"""Benchmark-only completion observer.

Runs in a disposable sidecar container on the benchmark network with the data
directory mounted. It asks ingestion to flush the WAL tail, then waits until
the backend's metadata index contains every offered span. It works for any
backend that keeps the documented metadata tables.
"""
import json
import os
import sqlite3
import sys
import time

expected = int(sys.argv[1])
deadline_seconds = float(sys.argv[2])

if len(sys.argv) == 3:
    import grpc
    from app.proto_gen import ingestion_pb2, ingestion_pb2_grpc

    started = time.perf_counter()
    with grpc.insecure_channel("ingestion:50052") as channel:
        response = ingestion_pb2_grpc.InternalIngestionServiceStub(channel).FlushWAL(
            ingestion_pb2.FlushWALRequest(),
            metadata=(("x-junjo-internal-token", os.environ["JUNJO_INTERNAL_GRPC_TOKEN"]),),
            timeout=120,
        )
        if not response.success:
            raise RuntimeError(str(response))
    flush_seconds = time.perf_counter() - started
    # Release gRPC and protobuf modules before waiting beside the indexer.
    os.execv(sys.executable, [sys.executable, __file__, str(expected), str(deadline_seconds), str(flush_seconds)])

flush_seconds = float(sys.argv[3])
started = time.perf_counter()
path = os.environ["JUNJO_METADATA_DB_PATH"]
observations = []
conn = None
while True:
    elapsed = time.perf_counter() - started
    if elapsed > deadline_seconds:
        print(json.dumps({"status": "deadline_exceeded", "indexed_rows": observations[-1]["indexed_rows"] if observations else None, "observations": observations}))
        raise SystemExit(3)
    try:
        if conn is None:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        rows, files = conn.execute("SELECT COALESCE(SUM(row_count),0),COUNT(*) FROM parquet_files").fetchone()
        failed = conn.execute("SELECT COUNT(*) FROM failed_parquet_files").fetchone()[0]
    except sqlite3.Error as error:
        observations.append({"seconds": elapsed, "error": str(error)})
        conn = None
        time.sleep(1)
        continue
    observations.append({"seconds": elapsed, "indexed_rows": rows, "indexed_files": files})
    if failed:
        raise RuntimeError(f"{failed} failed Parquet files")
    if os.environ.get("JUNJO_OBSERVER_AT_LEAST") == "1":
        # A real-world run also exports spans the harness does not count: the
        # freshness probe's and the real SDK's. Indexing is complete when the
        # offered spans are indexed and no cold file is left unindexed.
        on_disk = sum(
            name.endswith(".parquet")
            for _, _, names in os.walk("/app/.dbdata/spans/parquet")
            for name in names
        )
        if rows >= expected and files == on_disk:
            break
        time.sleep(1)
        continue
    if rows > expected:
        raise RuntimeError(f"Unexpected indexed row count: {rows} > {expected}")
    if rows == expected:
        break
    time.sleep(1)
result = {
    "status": "complete",
    "indexed_rows": rows,
    "indexed_files": files,
    "failed_files": failed,
    "flush_seconds": flush_seconds,
    "catchup_seconds": flush_seconds + (time.perf_counter() - started),
    "observations": observations,
    "distinct_traces": conn.execute("SELECT COUNT(DISTINCT trace_id) FROM trace_files").fetchone()[0],
    "llm_traces": conn.execute("SELECT COUNT(*) FROM llm_traces").fetchone()[0],
    "workflow_files": conn.execute("SELECT COUNT(*) FROM workflow_files").fetchone()[0],
    "agent_files": conn.execute("SELECT COUNT(*) FROM agent_files").fetchone()[0],
    "services": conn.execute("SELECT service_name,SUM(span_count) FROM file_services GROUP BY service_name ORDER BY service_name").fetchall(),
}
print(json.dumps(result))
