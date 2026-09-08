import json, subprocess
from pathlib import Path
root=Path('/tmp/junjo-robustness-20260906'); repo=Path('/Users/matt/repos/junjo')
for repetition in range(1,6):
 for case,size,iterations,warmup in [('scalar',0,30000,1000),('workflow',128,600,30)]:
  variants=['baseline','final'] if repetition%2 else ['final','baseline']
  for variant in variants:
   label=f'sdk-confirm-{variant}-{case}-r{repetition}'
   source=root/'sdk-baseline/src' if variant=='baseline' else repo/'sdks/python/src'
   cmd=['docker','run','--rm','--cpus','0.5','--memory','350m','--memory-swap','350m','-v',f'{source}:/source:ro','-v',f'{repo}/sdks/python/benchmarks:/bench:ro','-v',f'{root}:/evidence','-e','PYTHONPATH=/source','junjo-robustness-sdk:local','/bench/store_ownership.py','--case',case,'--size',str(size),'--iterations',str(iterations),'--warmup-iterations',str(warmup),'--label',label,'--output',f'/evidence/results/{label}.json']
   with (root/f'{label}.log').open('w') as log: result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
   if result.returncode: print('FAILED '+label,flush=True); raise SystemExit(result.returncode)
   d=json.loads((root/'results'/f'{label}.json').read_text()); print(label,round(d['operations_per_second']),round(d['cpu_us_per_operation'],2),d['peak_rss_mib'],flush=True)
