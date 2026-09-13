from pathlib import Path
import subprocess
r=Path('/tmp/junjo-mechanics-20260907')
for v in ['buffered-plain','resource-plain']:
 with (r/f'build-{v}.log').open('w') as log:
  p=subprocess.run(['docker','build','-f',str(r/v/'ingestion/Dockerfile'),'--target','production','-t',f'junjo-mechanics-{v}:local',str(r/v)],stdout=log,stderr=subprocess.STDOUT)
 print(v,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
