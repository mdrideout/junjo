import argparse, gc, hashlib, json, os, resource, time
from pathlib import Path
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
p=argparse.ArgumentParser();p.add_argument("--file",required=True);p.add_argument("--output",required=True);p.add_argument("--label",required=True);a=p.parse_args()
def rss():
    return int(next(x.split()[1] for x in Path("/proc/self/status").read_text().splitlines() if x.startswith("VmRSS:")))/1024
before=rss();cpu=time.process_time();start=time.perf_counter()
d=read_parquet_metadata(a.file,os.path.getsize(a.file))
elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu;after=rss();peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
h=hashlib.sha256()
for s in d.spans:
    h.update(repr((s.span_id,s.trace_id,s.parent_span_id,s.service_name,s.name,s.start_time,s.end_time,s.duration_ns,s.status_code,s.span_kind,s.is_root,s.junjo_span_type,s.openinference_span_kind,s.gen_ai_provider_name,s.gen_ai_operation_name)).encode())
assert len(d.spans)==d.row_count
result={"label":a.label,"rows":d.row_count,"seconds":elapsed,"cpu_seconds":cpu,"rows_per_second":d.row_count/elapsed,"cpu_us_per_row":cpu*1e6/d.row_count,"before_rss_mib":before,"after_rss_mib":after,"peak_rss_mib":peak,"semantic_sha256":h.hexdigest()}
del d;gc.collect();result["after_release_rss_mib"]=rss()
Path(a.output).write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))
