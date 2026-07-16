# Studio ingestion authorization baseline evidence

These raw JSON files were captured on 2026-07-16 from pinned revision
`390363caaffe4184fc278b5e7b3f774fdc41eaf5` and the L5 working-tree
implementation derived from it. The host was arm64 macOS 15.7.7 with Docker
29.5.3. Backend and ingestion each received 0.5 CPU; their memory limits were
450 MiB and 350 MiB.

The mixed-query comparison used 50 shared-key exporters, 100 exports per
exporter, 32 spans per export, a 100 ms start-to-start interval, and two
authenticated query workers. Each design completed 5,000 logical exports.

| Design | Runs | Median exports/s | Median export p95 | Median query p95 | Median ingestion peak RSS | Median max TCP records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Historical 600-second cache, fresh channel on miss | 3 | 504.28 | 13.48 ms | 47.02 ms | 55.21 MiB | 56 |
| Accepted 10-second bounded cache, reused channel | 3 | 504.31 | 17.11 ms | 40.68 ms | 24.11 MiB | 7 |
| No cache, fresh channel per export | 1 | 211.98 | 408.31 ms | 148.35 ms | 52.73 MiB | 4,991 |
| No cache, reused channel | 1 | 500.95 | 81.92 ms | 67.05 ms | 17.65 MiB | 6 |

The corresponding ingest-only files use the same export workload with zero
query workers. They separate ingestion capacity from mixed-query contention.

Files:

- `historical-600-fresh-r1.json`, `r2`, and `r3`: exact historical warm-cache
  implementation from the pinned revision.
- `bounded-10-reused-r1.json`, `r2`, and `r3`: accepted implementation.
- `no-cache-fresh.json`: pinned revision with only positive-cache read/write
  removed by the committed benchmark patch; fresh-channel behavior is
  unchanged.
- `no-cache-reused.json`: accepted transport with TTL zero.
- `historical-600-fresh-ingest-only.json`, `no-cache-fresh-ingest-only.json`,
  and `no-cache-reused-ingest-only.json`: ingest-only counterparts.

The benchmark patch and reproduction commands live in
[`apps/studio/ingestion/benchmarks`](../../../../apps/studio/ingestion/benchmarks/README.md).
The broader candidate and failure evidence lives in the
[authorization performance roadmap](../../STUDIO_INGESTION_API_KEY_AUTHORIZATION_PERFORMANCE.md).
