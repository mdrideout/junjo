import json,os,socket,subprocess
from pathlib import Path
r=Path('/tmp/junjo-mechanics-20260907');repo=Path('/Users/matt/repos/junjo/apps/studio');(r/'results').mkdir(exist_ok=True)
for shape,(exports,queries,interval) in {'sustained':(4000,0,0),'mixed':(300,2,100)}.items():
 for variant in ['old','drop','buffered']:
  label=f'profile-{variant}-{shape}'
  env={**os.environ,'JUNJO_BENCHMARK_PROJECT_NAME':'junjo-mechanics-benchmark','JUNJO_BENCHMARK_COMPOSE_ROOT':str(repo),'JUNJO_BENCHMARK_COMPOSE_OVERLAY':str(r/'profiles.yaml'),'JUNJO_BENCHMARK_IMAGE':f'junjo-mechanics-{variant}:local'}
  cmd=['uv','run','--project','backend','python',str(r/'benchmarks/auth_path_benchmark.py'),'--skip-build','--implementation-label',variant,'--exporters','50','--exports-per-exporter',str(exports),'--spans-per-export','32','--query-workers',str(queries),'--export-interval-ms',str(interval),'--skip-revocation','--wal-probe-spans','0','--verify-delivery','--recovery-seconds','10','--output',str(r/'results'/f'{label}.json')]
  with socket.socket() as a,socket.socket() as b:
   a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0));cmd+=['--backend-port',str(a.getsockname()[1]),'--ingestion-port',str(b.getsockname()[1])]
  print('START '+label,flush=True)
  with (r/f'{label}.log').open('w') as log:p=subprocess.run(cmd,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT)
  print('END '+label+' exit='+str(p.returncode),flush=True)
  if p.returncode:raise SystemExit(p.returncode)
