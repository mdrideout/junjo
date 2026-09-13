import cProfile, os, pstats
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
fixture='/fixture/cprofile-drop-mixed.parquet'
p=cProfile.Profile()
data=p.runcall(read_parquet_metadata,fixture,os.path.getsize(fixture))
assert len(data.spans)==data.row_count==121600
p.dump_stats('/evidence/offline/metadata-reader.pstats')
with open('/evidence/offline/metadata-reader-profile.txt','w') as out:
 pstats.Stats(p,stream=out).sort_stats('tottime').print_stats()
