import hashlib,json,os,socket,subprocess
from pathlib import Path
r=Path('/tmp/junjo-metadata-20260907');repo=Path('/Users/matt/repos/junjo/apps/studio')
jobs=[('baseline','long-confirm',600,2,100,1)]
for v,shape,exports,queries,interval,rep in jobs:
 label=f'accepted-e2e-{v}-{shape}-{rep}'
 env={**os.environ,'JUNJO_BENCHMARK_PROJECT_NAME':'junjo-metadata-benchmark','JUNJO_BENCHMARK_COMPOSE_ROOT':str(repo),'JUNJO_BENCHMARK_COMPOSE_OVERLAY':str(r/'overlay.yaml'),'JUNJO_METADATA_BACKEND_IMAGE':'junjo-durability-backend:local' if v=='baseline' else 'junjo-metadata-candidate:local'}
 env['JUNJO_METADATA_EXPECTED_SOURCE_SHA256']=json.dumps({dest:hashlib.sha256((r/v/name).read_bytes()).hexdigest() for name,dest in [('reader.py','/app/app/features/parquet_indexer/parquet_reader.py'),('indexer.py','/app/app/db_sqlite/metadata/indexer.py')]})
 cmd=['uv','run','--project','backend','python',str(r/'benchmarks/auth_path_benchmark.py'),'--skip-build','--implementation-label',label,'--exporters','50','--exports-per-exporter',str(exports),'--spans-per-export','32','--query-workers',str(queries),'--export-interval-ms',str(interval),'--skip-revocation','--wal-probe-spans','0','--verify-delivery','--recovery-seconds','0','--output',str(r/'results'/f'{label}.json')]
 with socket.socket() as a,socket.socket() as b:
  a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0));cmd+=['--backend-port',str(a.getsockname()[1]),'--ingestion-port',str(b.getsockname()[1])]
 print('START '+label,flush=True)
 with (r/f'{label}.log').open('w') as out:p=subprocess.run(cmd,cwd=repo,env=env,stdout=out,stderr=subprocess.STDOUT)
 print('END '+label+' exit='+str(p.returncode),flush=True)
 if p.returncode:raise SystemExit(p.returncode)
