import os, subprocess
from pathlib import Path
r=Path('/tmp/junjo-mechanics-20260907')
for rep,order in [(1,['baseline','slots']),(2,['slots','baseline']),(3,['baseline','slots'])]:
 for v in order:
  label=f'metadata-{v}-r{rep}'
  cmd=['docker','run','--rm','--cpus','0.5','--memory','450m','--memory-swap','450m','--entrypoint','python','-e','PYTHONPATH=/app','-v',f'{r}/metadata_read_bench.py:/benchmark/metadata_read_bench.py:ro','-v',f'{r}/metadata-reader-{v}.py:/app/app/features/parquet_indexer/parquet_reader.py:ro','-v',f'{r}/offline:/fixture:ro','-v',f'{r}:/evidence','junjo-durability-backend:local','/benchmark/metadata_read_bench.py','--file','/fixture/cprofile-drop-mixed.parquet','--output',f'/evidence/results/{label}.json','--label',label]
  print('START '+label,flush=True)
  with (r/f'{label}.log').open('w') as log: p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  print('END '+label+' exit='+str(p.returncode),flush=True)
  if p.returncode: raise SystemExit(p.returncode)
