import json
import os
from pathlib import Path
import subprocess
import socket
root=Path('/tmp/junjo-robustness-20260906')
repo=Path('/Users/matt/repos/junjo')
scenarios={
 'mixed':(50,300,32,2,100),
 'sustained':(50,4000,32,0,0),
 'serial':(1,1000,512,0,0),
 'sparse':(1,10000,1,0,0),
 'full-batch':(10,400,1000,0,0),
}
for repetition in range(1,4):
    for scenario,(exporters,exports,spans,queries,interval) in scenarios.items():
        variants=['baseline','candidate'] if repetition%2 else ['candidate','baseline']
        for variant in variants:
            label=f'ingestion-final-{variant}-{scenario}-r{repetition}'
            image='junjo-durability-baseline:local' if variant=='baseline' else 'junjo-robustness-try-send:local'
            env={**os.environ,'JUNJO_BENCHMARK_PROJECT_NAME':'junjo-robustness-benchmark',
                 'JUNJO_BENCHMARK_COMPOSE_OVERLAY':str(root/'images.yaml'),'JUNJO_BENCHMARK_IMAGE':image}
            args=['uv','run','--project','backend','python','ingestion/benchmarks/auth_path_benchmark.py','--skip-build',
                '--implementation-label',variant,'--exporters',str(exporters),'--exports-per-exporter',str(exports),
                '--spans-per-export',str(spans),'--query-workers',str(queries),'--export-interval-ms',str(interval),
                '--skip-revocation','--recovery-seconds','10','--verify-delivery','--wal-probe-spans','0','--output',str(root/'results'/f'{label}.json')]
            with socket.socket() as backend, socket.socket() as ingestion:
                backend.bind(('127.0.0.1',0)); ingestion.bind(('127.0.0.1',0))
                args+=['--backend-port',str(backend.getsockname()[1]),'--ingestion-port',str(ingestion.getsockname()[1])]
            print('START '+label,flush=True)
            with (root/f'{label}.log').open('w') as log:
                result=subprocess.run(args,cwd=repo/'apps/studio',env=env,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                print('FAILED '+label,flush=True)
                raise SystemExit(result.returncode)
            data=json.loads((root/'results'/f'{label}.json').read_text())
            print(label, json.dumps({'exports':data['exports'],'delivery':data['delivery'],'resources':data['resources']}),flush=True)
