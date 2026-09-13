import json,os,socket,subprocess
from pathlib import Path
r=Path('/tmp/junjo-mechanics-20260907');repo=Path('/Users/matt/repos/junjo/apps/studio')
(r/'plain.yaml').write_text('services:\n  backend:\n    image: junjo-durability-backend:local\n  ingestion:\n    image: ${JUNJO_BENCHMARK_IMAGE}\n')
(r/'shared-cpu.yaml').write_text('services:\n  backend:\n    image: junjo-durability-backend:local\n    cpuset: "0"\n    cpus: 0\n  ingestion:\n    image: ${JUNJO_BENCHMARK_IMAGE}\n    cpuset: "0"\n    cpus: 0\n')
images={'drop':'junjo-robustness-explicit-drop:local','buffered':'junjo-mechanics-buffered-plain:local','resource':'junjo-mechanics-resource-plain:local'}
(r/'split-cpu.yaml').write_text('services:\n  backend:\n    image: junjo-durability-backend:local\n    cpuset: "0"\n  ingestion:\n    image: ${JUNJO_BENCHMARK_IMAGE}\n    cpuset: "0"\n')
jobs=[('split-cpu-drop-long','drop','sustained','split-cpu',{}),('shared-cpu-drop-long','drop','sustained','shared-cpu',{})]
for label,v,shape,overlay,extras in jobs:
 exports,queries,interval=(8000,0,0) if shape=='sustained' else (300,2,100)
 env={**os.environ,'JUNJO_BENCHMARK_PROJECT_NAME':'junjo-mechanics-benchmark','JUNJO_BENCHMARK_COMPOSE_ROOT':str(repo),'JUNJO_BENCHMARK_COMPOSE_OVERLAY':str(r/f'{overlay}.yaml'),'JUNJO_BENCHMARK_IMAGE':images.get(v,'junjo-mechanics-drop:local'),**extras}
 cmd=['uv','run','--project','backend','python',str(r/'benchmarks/auth_path_benchmark.py'),'--skip-build','--implementation-label',label,'--exporters','50','--exports-per-exporter',str(exports),'--spans-per-export','32','--query-workers',str(queries),'--export-interval-ms',str(interval),'--skip-revocation','--wal-probe-spans','0','--verify-delivery','--recovery-seconds','10','--output',str(r/'results'/f'{label}.json')]
 with socket.socket() as a,socket.socket() as b:
  a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0));cmd+=['--backend-port',str(a.getsockname()[1]),'--ingestion-port',str(b.getsockname()[1])]
 print('START '+label,flush=True)
 with (r/f'{label}.log').open('w') as log:p=subprocess.run(cmd,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT)
 print('END '+label+' exit='+str(p.returncode),flush=True)
 if p.returncode:raise SystemExit(p.returncode)
