"""Benchmark-only completion observer, executed inside the disposable backend."""
import json,os,sqlite3,sys,time
if len(sys.argv)==2:
 import grpc
 from app.proto_gen import ingestion_pb2,ingestion_pb2_grpc
 expected=int(sys.argv[1]);started=time.perf_counter()
 with grpc.insecure_channel('ingestion:50052') as channel:
  response=ingestion_pb2_grpc.InternalIngestionServiceStub(channel).FlushWAL(ingestion_pb2.FlushWALRequest(),metadata=(('x-junjo-internal-token',os.environ['JUNJO_INTERNAL_GRPC_TOKEN']),))
  if not response.success:raise RuntimeError(str(response))
 # Release gRPC/protobuf modules and threads before waiting alongside the indexer.
 os.execv(sys.executable,[sys.executable,__file__,str(expected),str(started)])
expected=int(sys.argv[1]);started=float(sys.argv[2])
conn=sqlite3.connect(os.environ['JUNJO_METADATA_DB_PATH'])
observations=[]
while True:
 events=dict(line.split() for line in open('/sys/fs/cgroup/memory.events'))
 if int(events.get('oom_kill',0)):raise RuntimeError('Backend cgroup recorded an OOM kill during indexing')
 rows,files=conn.execute('SELECT COALESCE(SUM(row_count),0),COUNT(*) FROM parquet_files').fetchone()
 failed=conn.execute('SELECT COUNT(*) FROM failed_parquet_files').fetchone()[0]
 observations.append({'seconds':time.perf_counter()-started,'indexed_rows':rows,'indexed_files':files})
 if failed:raise RuntimeError(f'{failed} failed Parquet files')
 if rows>expected:raise RuntimeError(f'Unexpected indexed row count: {rows} > {expected}')
 if rows==expected:break
 time.sleep(1)
result={'indexed_rows':rows,'indexed_files':files,'failed_files':failed,'catchup_seconds':time.perf_counter()-started,'observations':observations,'distinct_traces':conn.execute('SELECT COUNT(DISTINCT trace_id) FROM trace_files').fetchone()[0],'llm_traces':conn.execute('SELECT COUNT(*) FROM llm_traces').fetchone()[0],'services':conn.execute('SELECT service_name,SUM(span_count) FROM file_services GROUP BY service_name ORDER BY service_name').fetchall()}
print(json.dumps(result))
