import subprocess
r='/tmp/junjo-metadata-20260907'
for rep,order in [(2,['baseline','candidate']),(3,['candidate','baseline']),(4,['baseline','candidate'])]:
 for v in order:
  p=subprocess.run(['python3',r+'/run_offline.py',v,str(rep)])
  if p.returncode:raise SystemExit(p.returncode)
