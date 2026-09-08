import subprocess,sys
from pathlib import Path
r=Path('/tmp/junjo-metadata-20260907')
v=sys.argv[1];rep=sys.argv[2]
for shape in ['observed','compact-agents','compact-unique-traces']:
 label=f'{v}-{shape}-{rep}'
 cmd=['docker','run','--rm','--cpus','0.5','--memory','450m','--memory-swap','450m','--entrypoint','python','-v',f'{r}:/evidence','-v',f'{r}/{v}/reader.py:/app/app/features/parquet_indexer/parquet_reader.py:ro','-v',f'{r}/{v}/indexer.py:/app/app/db_sqlite/metadata/indexer.py:ro','junjo-durability-backend:local','/evidence/offline.py','--fixture',f'/evidence/fixtures/{shape}.parquet','--output',f'/evidence/results/{label}.json']
 with (r/f'{label}.log').open('w') as out: p=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
 print(label,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
