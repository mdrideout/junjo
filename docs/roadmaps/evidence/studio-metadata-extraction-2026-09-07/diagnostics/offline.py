import argparse,gc,hashlib,json,os,resource,tempfile,time
from pathlib import Path
from app.db_sqlite.metadata.db import init_metadata_db,get_connection,close_connection
from app.db_sqlite.metadata.indexer import index_parquet_file
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
p=argparse.ArgumentParser();p.add_argument('--fixture',required=True);p.add_argument('--output',required=True);a=p.parse_args()
with tempfile.TemporaryDirectory() as tmp:
 init_metadata_db(tmp+'/metadata.db')
 start=time.perf_counter();cpu=time.process_time()
 data=read_parquet_metadata(a.fixture,os.path.getsize(a.fixture));read_wall=time.perf_counter()-start;read_cpu=time.process_time()-cpu
 indexed=index_parquet_file(data)
 result={'rows':indexed,'read_wall_seconds':read_wall,'read_cpu_seconds':read_cpu,'total_wall_seconds':time.perf_counter()-start,'total_cpu_seconds':time.process_time()-cpu,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
 assert indexed==data.row_count
 conn=get_connection();snapshot={}
 for table in ['parquet_files','trace_files','file_services','llm_traces','workflow_files','agent_files','failed_parquet_files']:
  cols=[x[1] for x in conn.execute('PRAGMA table_info('+table+')') if x[1] not in ['indexed_at','failed_at']]
  snapshot[table]=list(conn.execute('SELECT '+','.join(cols)+' FROM '+table+' ORDER BY '+','.join(cols)))
 result['semantic_sha256']=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest();result['table_rows']={k:len(v) for k,v in snapshot.items()}
 Path(a.output).write_text(json.dumps(result,indent=2)+'\n');close_connection()
print(json.dumps(result))
