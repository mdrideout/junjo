import json,os,subprocess,socket
from pathlib import Path
root=Path('/tmp/junjo-robustness-20260906');repo=Path('/Users/matt/repos/junjo')
variants={'old':'junjo-durability-baseline:local','tests':'junjo-robustness-baseline-rebuilt:local','drop':'junjo-robustness-explicit-drop:local'}
for rep,order in [(1,['drop']),(2,['drop','tests','old'])]:
 for variant in order:
  label=f'control-{variant}-sustained-r{rep}'
  env={**os.environ,'JUNJO_BENCHMARK_PROJECT_NAME':'junjo-robustness-benchmark','JUNJO_BENCHMARK_COMPOSE_OVERLAY':str(root/'images.yaml'),'JUNJO_BENCHMARK_IMAGE':variants[variant]}
  cmd=['uv','run','--project','backend','python','ingestion/benchmarks/auth_path_benchmark.py','--skip-build','--implementation-label',variant,'--exporters','50','--exports-per-exporter','4000','--spans-per-export','32','--query-workers','0','--export-interval-ms','0','--skip-revocation','--wal-probe-spans','0','--verify-delivery','--recovery-seconds','10','--output',str(root/'results'/f'{label}.json')]
  with socket.socket() as b,socket.socket() as i:
   b.bind(('127.0.0.1',0));i.bind(('127.0.0.1',0));cmd+=['--backend-port',str(b.getsockname()[1]),'--ingestion-port',str(i.getsockname()[1])]
  print('START '+label,flush=True)
  with (root/f'{label}.log').open('w') as log: p=subprocess.run(cmd,cwd=repo/'apps/studio',env=env,stdout=log,stderr=subprocess.STDOUT)
  if p.returncode:print('FAILED '+label,flush=True);raise SystemExit(p.returncode)
  d=json.loads((root/'results'/f'{label}.json').read_text());print(label,round(d['exports']['spans_per_second']),d['container_after']['ingestion']['cpu_usage_seconds']-d['container_before']['ingestion']['cpu_usage_seconds'],flush=True)
