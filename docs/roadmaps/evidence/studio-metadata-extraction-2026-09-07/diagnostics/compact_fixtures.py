import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
p=Path('/evidence/fixtures')
for shape in ['agents','unique-traces']:
 t=pq.read_table(p/(shape+'.parquet'))
 values=[]
 for a in t.column('attributes').to_pylist():
  a=json.loads(a);a.pop('input');a['prompt']='Synthetic request: 日本語';values.append(json.dumps(a))
 i=t.schema.get_field_index('attributes');t=t.set_column(i,t.schema.field(i),pa.array(values))
 pq.write_table(t,p/('compact-'+shape+'.parquet'),compression='lz4')
