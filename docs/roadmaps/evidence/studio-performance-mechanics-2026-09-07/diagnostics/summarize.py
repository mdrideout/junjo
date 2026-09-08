import json, statistics
from pathlib import Path
r=Path('/Users/matt/repos/junjo/docs/roadmaps/evidence/studio-performance-mechanics-2026-09-07')
summary={'runs':{},'profiles':{},'metadata_runs':{}}
for p in sorted((r/'results').glob('*.json')):
 d=json.loads(p.read_text())
 if 'exports' not in d:
  summary['metadata_runs'][p.stem]=d;continue
 e=d['exports'];a=d['container_after'];b=d['container_before'];n=e['acknowledged_spans'];cpu={k:a[k]['cpu_usage_seconds']-b[k]['cpu_usage_seconds'] for k in ['ingestion','backend']}
 summary['runs'][p.stem]={'spans_per_second':e['spans_per_second'],'workload_seconds':e['workload_seconds'],'offered_spans':e['offered_spans'],'acknowledged_spans':n,'export_p95_ms':e['p95_ms'],'query_p95_ms':d['queries'].get('p95_ms'),'cpu_seconds':cpu,'ingestion_cpu_us_per_span':cpu['ingestion']*1e6/n,'peak_sampled_working_set_mib':{k:v['max_memory_mib'] for k,v in d['resources'].items()},'ingestion_throttled_seconds':(a['ingestion']['cpu_stat']['throttled_usec']-b['ingestion']['cpu_stat']['throttled_usec'])/1e6,'ingestion_throttled_periods':a['ingestion']['cpu_stat']['nr_throttled']-b['ingestion']['cpu_stat']['nr_throttled'],'ingestion_periods':a['ingestion']['cpu_stat']['nr_periods']-b['ingestion']['cpu_stat']['nr_periods'],'acceptance':d['acceptance'],'delivery':d['delivery']}
 assert all(d['acceptance'].values()) and n==d['delivery']['persisted_acknowledged_spans']==e['offered_spans']
 log=p.with_suffix('.services.log')
 for line in log.read_text().splitlines():
  for marker,kind in [('JUNJO_PROFILE ','ingestion'),('JUNJO_BACKEND_PROFILE ','backend')]:
   if marker in line:summary['profiles'].setdefault(p.stem,{})[kind]=json.loads(line.split(marker,1)[1])
summary['totals']={'e2e_runs':len(summary['runs']),'offered_acknowledged_persisted_spans':sum(x['acknowledged_spans'] for x in summary['runs'].values()),'missing_acknowledged_spans':sum(x['delivery']['missing_acknowledged_spans'] for x in summary['runs'].values()),'duplicate_rows':sum(x['delivery']['duplicate_rows'] for x in summary['runs'].values())}
summary['prototype_medians']={}
for v in ['drop','buffered','resource']:
 xs=[d for k,d in summary['runs'].items() if k.startswith(f'plain-{v}-sustained-r')]
 summary['prototype_medians'][v]={k:statistics.median(x[k] for x in xs) for k in ['spans_per_second','ingestion_cpu_us_per_span']}
base=summary['prototype_medians']['drop']
for d in summary['prototype_medians'].values():d['throughput_change_percent']=100*(d['spans_per_second']/base['spans_per_second']-1)
summary['metadata_medians']={}
for v in ['baseline','slots']:
 xs=[d for k,d in summary['metadata_runs'].items() if k.startswith(f'metadata-{v}-')]
 summary['metadata_medians'][v]={k:statistics.median(x[k] for x in xs) for k in ['seconds','cpu_seconds','peak_rss_mib']}
assert len({x['semantic_sha256'] for x in summary['metadata_runs'].values()})==1
(r/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ['totals','prototype_medians','metadata_medians']},indent=2))
