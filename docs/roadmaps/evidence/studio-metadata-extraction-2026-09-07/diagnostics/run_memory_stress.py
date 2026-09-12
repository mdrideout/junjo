import json,subprocess
from pathlib import Path
r=Path('/tmp/junjo-metadata-20260907')
for v in ['baseline','candidate']:
 name='junjo-metadata-memory-'+v
 cmd=['docker','run','--name',name,'--cpus','0.5','--memory','450m','--memory-swap','450m','--entrypoint','python','-v',f'{r}:/evidence','-v',f'{r}/{v}/reader.py:/app/app/features/parquet_indexer/parquet_reader.py:ro','-v',f'{r}/{v}/indexer.py:/app/app/db_sqlite/metadata/indexer.py:ro','junjo-durability-backend:local','/evidence/offline.py','--fixture','/evidence/fixtures/agents.parquet','--output',f'/evidence/results/memory-stress-{v}.json']
 with (r/f'memory-stress-{v}.log').open('w') as out:p=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
 info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 result={'exit_code':p.returncode,'state':info['State'],'memory_limit_bytes':info['HostConfig']['Memory'],'memory_swap_bytes':info['HostConfig']['MemorySwap'],'nano_cpus':info['HostConfig']['NanoCpus'],'image':info['Image']}
 (r/f'{v}-memory-stress.json').write_text(json.dumps(result,indent=2)+'\n')
 subprocess.run(['docker','rm',name],check=True,stdout=subprocess.DEVNULL)
 print(v,p.returncode,info['State']['OOMKilled'],flush=True)
