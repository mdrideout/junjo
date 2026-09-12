import os, subprocess
from pathlib import Path
r=Path('/tmp/junjo-mechanics-20260907')
for v in ['buffered-plain','resource-plain']:
 env={**os.environ,'CARGO_TARGET_DIR':'/Users/matt/repos/junjo/apps/studio/ingestion/target'}
 with (r/f'test-{v}.log').open('w') as log:
  p=subprocess.run(['cargo','test','--locked','--manifest-path',str(r/v/'ingestion/Cargo.toml')],cwd=r/v/'ingestion',env=env,stdout=log,stderr=subprocess.STDOUT)
 print(v,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
