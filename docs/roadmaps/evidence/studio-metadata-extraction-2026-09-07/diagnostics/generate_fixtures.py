import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
p=Path('/evidence/fixtures');table=pq.read_table('/seed.parquet');pq.write_table(table,p/'observed.parquet',compression='lz4')
n=table.num_rows
attrs=[{}, {'openinference.span.kind':'LLM'}, {'gen_ai.provider.name':'xai'},{'gen_ai.operation.name':'chat'},{'junjo.span_type':'workflow'}, {'junjo.span_type':'agent'}, {'junjo.span_type':'node'}]
encoded=[json.dumps({**v,'input':{'messages':[{'role':'user','content':'Synthetic benchmark: 日本語 '+('example '*16)}]*4},'model':'synthetic','output':{'tokens':128}}) for v in attrs]
for name,unique in [('agents',False),('unique-traces',True)]:
 t=table
 for field,values in [('attributes',[encoded[i%len(encoded)] for i in range(n)]),('service_name',['service-'+str(i%3) for i in range(n)]),('trace_id',[f'{(i if unique else i//32):032x}' for i in range(n)])]:
  idx=t.schema.get_field_index(field);t=t.set_column(idx,t.schema.field(field),pa.array(values,type=t.schema.field(field).type))
 pq.write_table(t,p/(name+'.parquet'),compression='lz4')
print(n)
