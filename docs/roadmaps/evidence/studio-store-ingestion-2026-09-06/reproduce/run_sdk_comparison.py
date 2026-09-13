import json
import subprocess
from pathlib import Path
root=Path('/tmp/junjo-robustness-20260906')
repo=Path('/Users/matt/repos/junjo')
cases=[('scalar',0,5000),('scalar',8192,300),('replace',32,3000),('replace',8192,300),('noop',8192,300),('prospective',8192,300),('workflow',128,150)]
for repetition in range(1,4):
    variants=['baseline','copy-patch','merged']
    variants=variants[repetition-1:]+variants[:repetition-1]
    for case,size,iterations in cases:
        for variant in variants:
            label=f'sdk-{variant}-{case}-{size}-r{repetition}'
            command=['docker','run','--rm','--cpus','0.5','--memory','350m','--memory-swap','350m',
              '-v',f'{root}:/evidence','-v',f'{repo}/sdks/python/benchmarks:/bench:ro',
              '-e',f'PYTHONPATH=/evidence/sdk-{variant}/src','junjo-robustness-sdk:local',
              '/bench/store_ownership.py','--case',case,'--size',str(size),'--iterations',str(iterations),
              '--label',label,'--output',f'/evidence/results/{label}.json']
            with (root/f'{label}.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                print(label+' FAILED',flush=True)
                raise SystemExit(result.returncode)
            data=json.loads((root/'results'/f'{label}.json').read_text())
            print(label,round(data['operations_per_second'],2),round(data['cpu_us_per_operation'],2),data['peak_rss_mib'],flush=True)
