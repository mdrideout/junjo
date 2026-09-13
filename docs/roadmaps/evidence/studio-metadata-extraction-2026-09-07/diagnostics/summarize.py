import json,statistics
from pathlib import Path
r=Path('/tmp/junjo-metadata-20260907')
out={'offline':{},'e2e':{},'failures':{}}
for shape in ['observed','compact-agents','compact-unique-traces']:
 groups={v:[json.loads((r/'results'/f'{v}-{shape}-{i}.json').read_text()) for i in [2,3,4]] for v in ['baseline','candidate']}
 assert len({d['semantic_sha256'] for ds in groups.values() for d in ds})==1
 m={v:{k:statistics.median(d[k] for d in ds) for k in ['rows','read_cpu_seconds','total_cpu_seconds','total_wall_seconds','peak_rss_mib']} for v,ds in groups.items()}
 m['change_percent']={k:100*(m['candidate'][k]/m['baseline'][k]-1) for k in ['read_cpu_seconds','total_cpu_seconds','total_wall_seconds','peak_rss_mib']};out['offline'][shape]=m
for p in sorted((r/'results').glob('accepted-e2e-*.json')):
 if p.name.endswith('.ingestion-phase.json'):continue
 d=json.loads(p.read_text())
 if 'exports' not in d or not all(d['acceptance'].values()):
  out['failures'][p.stem]=d;continue
 before=d['container_before'];after=d['container_after'];ingafter=d['container_after_ingestion'];index=d['indexing'];exports=d['exports'];n=exports['offered_spans']
 assert all(d['acceptance'].values())
 assert index['indexed_rows']==exports['acknowledged_spans']==d['delivery']['persisted_acknowledged_spans']==n
 assert index['distinct_traces']==index['llm_traces']==exports['requested']
 out['e2e'][p.stem]={'offered_acknowledged_persisted_indexed_rows':n,'ingestion_spans_per_second':exports['spans_per_second'],'export_p95_ms':exports['p95_ms'],'export_p99_ms':exports['p99_ms'],'query_p95_during_ingestion_ms':d['queries_during_ingestion']['p95_ms'],'query_p95_through_index_completion_ms':d['queries']['p95_ms'],'query_p99_through_index_completion_ms':d['queries']['p99_ms'],'completed_queries':d['queries']['result_codes'].get('200',0),'total_completion_seconds':d['completed_work_seconds'],'index_catchup_seconds':index['catchup_seconds'],'cpu_seconds_through_indexing':{k:after[k]['cpu_usage_seconds']-before[k]['cpu_usage_seconds'] for k in before},'cpu_seconds_during_ingestion':{k:ingafter[k]['cpu_usage_seconds']-before[k]['cpu_usage_seconds'] for k in before},'peak_sampled_working_set_mib':{k:v['max_memory_mib'] for k,v in d['resources'].items()},'canonical_duplicate_rows':d['delivery']['duplicate_rows'],'indexed_files':index['indexed_files']}
out['e2e_medians']={}
for shape in ['mixed','saturation']:
 groups={v:[d for k,d in out['e2e'].items() if k.startswith(f'accepted-e2e-{v}-{shape}-')] for v in ['baseline','candidate']}
 if not all(groups.values()):continue
 med={v:{**{k:statistics.median(d[k] for d in ds) for k in ['ingestion_spans_per_second','export_p95_ms','query_p95_during_ingestion_ms','query_p95_through_index_completion_ms','completed_queries','total_completion_seconds']},'backend_cpu_seconds':statistics.median(d['cpu_seconds_through_indexing']['backend'] for d in ds),'ingestion_cpu_seconds':statistics.median(d['cpu_seconds_through_indexing']['ingestion'] for d in ds),'backend_peak_mib':statistics.median(d['peak_sampled_working_set_mib']['backend'] for d in ds)} for v,ds in groups.items()}
 med['change_percent']={k:100*(med['candidate'][k]/med['baseline'][k]-1) for k in med['baseline'] if med['baseline'][k]};out['e2e_medians'][shape]=med
out['totals']={'successful_e2e_runs':len(out['e2e']),'failed_e2e_runs':len(out['failures']),'offered_acknowledged_persisted_indexed_rows':sum(d['offered_acknowledged_persisted_indexed_rows'] for d in out['e2e'].values())}
(r/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'offline':out['offline'],'e2e_medians':out['e2e_medians'],'totals':out['totals']},indent=2))
