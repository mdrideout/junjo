# Rust backend, final image — October 4, 2026

This is the comparison on the final image that work package 9 of the
[Studio backend Rust migration plan](../../STUDIO_BACKEND_RUST_MIGRATION.md)
requires, and the measurement of Parquet filter pushdown that the plan's
decision 10 left open. The plan sets no pass threshold. The results are
presented here and the maintainer decides.

The maintainer decided on 2026-10-04 to turn filter pushdown on. The released
default is therefore the "Rust, pushdown on" column below, and "Decision and
confirmation" records the check of the default image.

Both backends completed the same work in every run.

- **Backend CPU**: 43% less while ingesting with concurrent queries, and 84%
  less in the index-completion workload.
- **Backend memory**: peak sampled memory of 56–79 MiB against 287–350 MiB.
  About 7 MiB of anonymous memory at idle against 99 MiB.
- **Service queries**: p95 of 13.2 ms against 30.9 ms, with 2% more queries
  answered in the same window.
- **Ingestion with separate CPU quotas**: throughput, ingestion CPU, and export
  latency are unchanged.
- **Ingestion on one shared CPU**: equal in the mixed workload. In the burst
  workload the Rust indexer's cycle fell inside the burst and ingestion was
  3.5% slower; the Python indexer's cycle fell after it.
- **One container fewer**: the application image also serves the UI, so the
  frontend container, about 10 MiB, is gone.

- **Trace and listing queries**, measured here for the first time: 58% and
  50% less backend CPU than Python, with mean latency of 87 ms against 208 ms
  and 145 ms against 287 ms.
- **Parquet filter pushdown**, the setting left open: turning it on halves
  the Rust backend's CPU for both of those queries again, with the same
  results and no more memory.
- **Listing queries while unflushed spans exist**, found after the decision:
  with as few as 32 unflushed spans a listing costs about 1 s of backend CPU
  where it costs 0.016 s without them, and some fail. The Python backend
  failed every one and restarted. See "Listing queries while unflushed spans
  exist".
- **The real frontend and SDK while spans arrive**, the test the maintainer
  asked for. Two changes were prototyped, measured, and adopted on the
  maintainer's decision. What they gain depends on how many spans a listing
  matches. Where every span was a root span, the Traces list went from about
  11 s at the 95th percentile to 0.4 s, and failed requests from 12 of 1,407
  to none of 8,376. Where one span in 32 was a root span, the tree completed
  about 20% more page loads, failed none of 11,999 requests where 7 of 5,145
  had failed, and peaked at about 132 MiB against 163. See "Real-world runs"
  and "The adopted build".
- **The default Traces view**, which those runs showed to be missing its
  newest traces after every flush: 15% of loads at the standard load and
  about half at four times the load. Two variants of a fix were measured,
  and the maintainer chose the second, which is now in the tree. On the
  tree's build no default view was short in 1,291 loads at the standard load
  or in 278 at four times the load. It completed about 6% fewer page loads
  than the build before it, and the default view took about 500 ms at the
  median against about 410 ms. See "The default Traces view".
- **Queries beside live ingestion**, also measured after the decision: with
  eight concurrent readers one Rust trace query in about 5,400 failed because
  ingestion replaced or removed the hot snapshot under it. No Python query
  failed. See "Queries while spans arrive".

**29 runs; 29,120,000 offered spans, all acknowledged, all verified in
canonical storage after shutdown, and all indexed.** No OOM kills and no
container restarts. The Python backend reached its 450 MiB limit in 8 of its
13 runs, which forces reclaim but did not kill it. The Rust backend never
reached the limit in 16 runs.

Eighty-three more runs were made on 2026-10-04: for the decision on filter
pushdown, for the finding that followed it, for queries beside live
ingestion, with the real frontend and SDK, and then of the adopted build, of
two prototypes for the default Traces view, and of the one that was adopted. They are reported in their own
sections and are not part of the counts above.

## What was compared

- **Python**: the Studio 0.85.0 production image, built from an export of the
  published revision `1b5a798`.
- **Rust**: the application image built from this working tree at Studio
  0.85.0: the complete backend, with the telemetry contract 3 evidence logic,
  and the built UI. Release profile with link-time optimization, system
  allocator. The first comparison, on 2026-10-03, measured a slice of this
  backend against the 0.84.1 Python backend; see
  [that evidence](../studio-backend-rust-2026-10-03/README.md).
- **Ingestion**: one production image at 0.85.0, identical for every run.
- **Profiles, workloads, windows, and the meaning of completed work** are the
  ones the first comparison describes. Results are from the split quota
  profile unless a section says otherwise.
- **Host condition**: every run used the loaded host, four busy loops in a
  sibling container, which the first comparison found necessary for CPU and
  latency to be comparable.
- **Order**: runs were sequential, Python and Rust alternated, and no build or
  test suite ran during the batch.

Both backends produced identical index contents in every run: the same file,
row, and trace counts, the same per-service span counts, and the same LLM,
Workflow, and Agent classification counts.

## Results on the split quota profile

Medians, with ranges in parentheses. Three runs of each backend per workload.

### Mixed workload

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 480,000 | 480,000 | — |
| Backend CPU during ingestion | 6.44 s (6.38–6.66) | 3.66 s (3.65–3.70) | −43% |
| Backend CPU through completed indexing | 9.86 s (9.76–10.48) | 4.50 s (4.47–4.52) | −54% |
| Peak sampled backend memory | 302.6 MiB (287.0–350.4) | 77.4 MiB (77.4–79.2) | −74% |
| Backend cgroup peak, including file cache | 450.0 MiB (at the limit) | 89.8 MiB (88.6–90.6) | −80% |
| Backend anonymous memory at idle | 98.7 MiB | 7.4 MiB | −93% |
| Backend process RSS at idle | 157.8 MiB (156.7–158.0) | 22.9 MiB | −85% |
| Backend anonymous memory after the work | 263.5 MiB (242.4–263.9) | 13.2 MiB (13.0–13.3) | −95% |
| Backend process RSS after the work | 333.1 MiB (326.9–349.0) | 48.2 MiB (48.0–48.5) | −86% |
| Service queries answered before and during ingestion | 1,767 (1,746–1,771) | 1,810 (1,807–1,824) | +2% |
| Service-query p95, same window | 30.9 ms (30.1–31.5) | 13.2 ms (12.7–14.9) | −57% |
| Service-query p99, same window | 67.9 ms (64.1–110.7) | 39.6 ms (38.8–49.0) | −42% |
| Export p95 | 8.10 ms (7.61–8.36) | 7.34 ms (7.34–7.50) | within range |
| Export p99 | 28.9 ms (21.8–43.2) | 20.9 ms (15.4–33.3) | within range |
| Ingestion CPU during ingestion | 2.26 s (2.20–2.35) | 2.22 s (2.21–2.27) | flat |
| Backend CPU throttled by its quota, through completed indexing | 1.97 s (1.91–2.12) | 0.26 s (0.22–0.31) | −87% |

The before-ingestion window of this workload already has the two query workers
running, as the first comparison explains, so its "at idle" rows are readings
before any span arrives, not readings of an untouched process. The
index-completion workload below has no query workers, and its idle readings
are the same to within 1 MiB of anonymous memory.

### Index-completion workload

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 1,280,000 | 1,280,000 | — |
| Backend CPU through completed indexing | 4.17 s (4.16–4.18) | 0.68 s (0.66–0.70) | −84% |
| Peak sampled backend memory | 312.0 MiB (293.6–336.8) | 55.6 MiB (55.5–69.7) | −82% |
| Backend cgroup peak, including file cache | 450.0 MiB (448.0–450.0) | 88.6 MiB (87.6–89.4) | −80% |
| Backend anonymous memory at idle | 98.6 MiB (98.5–98.6) | 7.1 MiB | −93% |
| Backend process RSS at idle | 144.3 MiB (141.3–153.5) | 22.0 MiB (21.6–22.0) | −85% |
| Backend anonymous memory after the work | 241.0 MiB (225.0–244.4) | 18.5 MiB (18.5–18.6) | −92% |
| Backend process RSS after the work | 288.2 MiB (274.3–292.3) | 36.6 MiB (36.5–36.8) | −87% |
| Acknowledged ingestion rate | 180,656 spans/s (180,235–181,244) | 179,357 spans/s (177,027–181,273) | flat |
| Export p95 | 54.1 ms (54.0–54.3) | 54.3 ms (53.9–54.3) | flat |
| Ingestion CPU during ingestion | 3.55 s (3.53–3.56) | 3.59 s (3.54–3.63) | flat |

### Completion time is still set by the polling cadence

Ingestion and indexing completed in 40.1 s (40.0–41.1) beside Python and
34.1 s (34.0–34.2) beside Rust in the mixed workload, and in 44.5 s and
34.3 s in the index-completion workload. As the first comparison explains,
these are not indexing speeds: both backends index at most 10 files per cycle
and wait 30 seconds between cycles, so the total depends on where the cycles
fall. The Rust figures here differ from the slice's for the same reason.

## Results on the single CPU profile

Both services share one CPU with no individual quota. The load is pinned to
other CPUs. Two runs in every cell.

### Mixed workload

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 480,000 | 480,000 | — |
| Backend CPU during ingestion | 5.96 s (5.93–5.98) | 3.58 s (3.56–3.59) | −40% |
| Backend CPU through completed indexing | 9.40 s (9.19–9.62) | 4.39 s (4.37–4.41) | −53% |
| Peak sampled backend memory | 296.2 MiB (278.2–314.2) | 76.1 MiB (76.0–76.2) | −74% |
| Backend process RSS after the work | 274.5 MiB (267.5–281.5) | 48.0 MiB (47.8–48.1) | −83% |
| Service queries answered before and during ingestion | 1,777 (1,767–1,787) | 1,855 (1,854–1,856) | +4% |
| Service-query p95, same window | 29.6 ms (28.2–31.0) | 12.8 ms (12.5–13.1) | −57% |
| Export p95 | 8.14 ms (8.09–8.20) | 7.27 ms (7.19–7.34) | −11% |
| Ingestion CPU during ingestion | 2.20 s | 2.17 s (2.15–2.18) | flat |

### Index-completion workload

| | Python | Rust | Change |
| --- | ---: | ---: | ---: |
| Spans acknowledged, persisted, and indexed | 1,280,000 | 1,280,000 | — |
| Backend CPU through completed indexing | 4.15 s (4.02–4.28) | 0.67 s (0.66–0.68) | −84% |
| Backend CPU inside the ingestion burst | 0.04 s | 0.32 s | see below |
| Acknowledged ingestion rate | 330,467 spans/s (321,256–339,677) | 318,823 spans/s (314,468–323,178) | −3.5% |
| Export p95 | 5.97 ms (5.63–6.32) | 8.13 ms (8.00–8.26) | +36% |
| Ingestion CPU during ingestion | 3.74 s (3.64–3.83) | 3.58 s (3.58–3.59) | −4% |
| Peak sampled backend memory | 247.0 MiB (239.2–254.7) | 71.7 MiB (71.4–72.0) | −71% |

The burst lasts about four seconds on this profile. In both Rust runs an
indexing cycle fell inside it: ten files were already indexed when ingestion
ended, at a cost of 0.32 s of backend CPU on the shared CPU. In both Python
runs the cycle fell after the burst: no file was indexed when ingestion
ended. The difference in rate and export latency is the cost of indexing ten
files during a burst on one CPU, which the first comparison measured for both
backends: 6% beside Rust and 33% beside Python. This batch has no Python run
with the cycle inside the burst.

## Trace and listing queries, and filter pushdown

The first comparison could not measure filtered queries: the slice had no
workload for them, and decision 10 kept Parquet filter pushdown off until one
existed. This phase runs after the index-completion workload has finished, on
1,280,000 indexed spans in 16 cold files, with nothing else using the backend.
Two workers, split quota profile, three runs of each variant.

- **Trace queries**: 200 distinct traces, spread over every exporter and the
  whole run. Each trace is 32 spans in one cold file, so the filter matches
  32 of about 80,000 rows in the file the metadata index selects.
- **Listing queries**: 60 requests for a service's most recent root spans, at
  the default page size. The filter matches a third of the rows.

Every query answered 200 with the same number of rows for every variant: 32
spans for each trace and 100 for each listing.

| | Python | Rust | Rust, pushdown on |
| --- | ---: | ---: | ---: |
| Trace queries: backend CPU for 200 | 10.44 s (10.36–10.53) | 4.40 s (4.39–4.42) | 2.22 s (2.13–2.24) |
| Trace queries: mean | 207.8 ms (207.1–209.7) | 87.0 ms (86.9–88.1) | 43.9 ms (41.9–44.1) |
| Trace queries: p50 | 203.9 ms (202.8–204.5) | 93.2 ms (93.1–93.6) | 22.0 ms (21.1–23.8) |
| Trace queries: p95 | 265.6 ms (258.9–267.7) | 105.2 ms (102.8–105.8) | 80.1 ms (79.8–83.1) |
| Listing queries: backend CPU for 60 | 4.37 s (4.34–4.43) | 2.20 s (2.19–2.22) | 0.95 s (0.93–1.00) |
| Listing queries: mean | 287.4 ms (287.0–294.0) | 144.6 ms (144.4–144.6) | 61.4 ms (61.0–64.8) |
| Listing queries: p95 | 311.4 ms (311.1–357.8) | 190.8 ms (182.2–193.1) | 93.3 ms (92.3–95.7) |
| Backend cgroup peak after both | 450.0 MiB (at the limit) | 103.1 MiB (102.3–103.7) | 103.0 MiB (96.0–109.2) |
| Backend process RSS after both | 369.8 MiB (358.6–378.7) | 64.7 MiB (64.3–64.8) | 59.8 MiB (59.1–64.5) |
| Backend anonymous memory after both | 306.1 MiB (302.4–312.6) | 25.8 MiB (25.6–26.8) | 24.7 MiB (23.8–25.2) |

Read the latencies with the quota in mind. Two workers ask for more than the
backend's half CPU, so a query waits for quota as well as for work. Backend
CPU is the measure of cost; latency follows it.

- **Rust against Python**, both without pushdown: 58% less CPU per trace
  query and 50% less per listing query.
- **Pushdown on against off**, same Rust image: 50% less CPU per trace query
  and 57% less per listing query. Memory is the same to within the range of
  the runs.
- The 223 server tests, which include the cold, hot, and bridged query tests
  over every fixture, also pass with pushdown turned on in the test
  configuration.

The index-completion part of these runs matches the index-completion workload
above for all three variants.

This is the evidence decision 10 waited for. These runs switched pushdown
with `JUNJO_DIAGNOSTIC_DF_PUSHDOWN_FILTERS`, a measurement-only variable that
also turned on filter reordering.

A first batch of these runs asked for trace identities this workload never
writes, so every trace query found nothing. Those runs were discarded.

## Decision and confirmation

The maintainer turned filter pushdown on, with filter reordering, on
2026-10-04. The variable that switched it was removed, and
[Studio ADR-011](../../../../apps/studio/docs/adr/011-rust-backend-and-single-origin-studio.md)
carries the amendment.

An image built from that tree, with no variable, was then run beside the
earlier image with the variable off and on: nine interleaved runs of the same
filtered-query workload on the same profile and loaded host.

| | Earlier image, pushdown off | Earlier image, variable on | New default image |
| --- | ---: | ---: | ---: |
| Runs counted | 2 | 2 | 3 |
| Trace queries: backend CPU for 200 | 4.41 s, 4.29 s | 2.14 s, 2.13 s | 2.17 s (2.13–2.18) |
| Trace queries: mean | 87.5 ms, 84.9 ms | 42.4 ms, 42.2 ms | 42.6 ms (42.2–43.1) |
| Trace queries: p95 | 107.2 ms, 102.3 ms | 79.2 ms, 80.8 ms | 77.2 ms (76.4–78.0) |
| Listing queries: backend CPU for 60 | 2.17 s, 2.22 s | 0.92 s, 1.00 s | 0.94 s (0.90–0.98) |
| Listing queries: mean | 142.3 ms, 145.9 ms | 57.8 ms, 64.9 ms | 59.3 ms (57.0–61.9) |
| Listing queries: p95 | 191.9 ms, 187.4 ms | 90.1 ms, 98.9 ms | 90.9 ms (85.2–91.9) |
| Backend cgroup peak after both | 103.0 MiB, 102.5 MiB | 81.3 MiB, 87.1 MiB | 97.5 MiB (96.2–101.6) |
| Backend process RSS after both | 61.7 MiB, 60.0 MiB | 62.5 MiB, 64.0 MiB | 62.5 MiB (61.1–63.5) |

The new default image does what the measured variant did. Every counted query
answered 200 with the same rows as before.

The first run of each earlier-image variant is not counted. The batch started
six seconds after the image build ended, and both were disturbed.

- In the pushdown-off run, 43 of 40,000 exports ended `UNAVAILABLE` after
  their retries, so the run was not accepted, the harness did not wait for
  indexing, and its queries ran while spans were still unflushed. That is how
  the next section's cost was first seen.
- In the variable-on run all work completed, but ingestion used 3.7 s of CPU
  during the trace queries against 0.06–0.12 s in the undisturbed runs, and
  the trace queries cost 11.1 s of backend CPU. The cause was not
  established.

Both runs are in the summary of the decision runs.

## Listing queries while unflushed spans exist

Every query measurement above ran after everything was flushed, so each query
read cold files only. With a hot snapshot present, a query also has to drop a
hot span that a cold file already holds. It does that by numbering the rows
of both tiers per trace and span identifier, which sorts every matching span
with all of its columns before the newest page is cut. With cold files only,
the engine keeps just the newest page.

Unflushed spans are the normal state of a service that is receiving
telemetry: ingestion flushes at a size or age threshold, not continuously.

The filtered workload was run again with 32 spans exported after indexing
completed and left unflushed: 200 trace queries, then 20 listing queries, two
workers, the same profile. Each listing reads the 16 cold files, in which
about 427,000 spans match the service.

| | Rust, nothing unflushed | Rust, 32 unflushed spans | Python, 32 unflushed spans |
| --- | ---: | ---: | ---: |
| Runs | 3 | 2 | 2 |
| Trace queries answered | 200 of 200 | 200 of 200 | 200 of 200 |
| Trace queries: backend CPU for 200 | 2.17 s | 2.84 s, 2.90 s | 11.19 s, 11.25 s |
| Listing queries answered | 60 of 60 | 14 of 20, 18 of 20 | 0 of 20, 0 of 20 |
| Listing queries: backend CPU each | 0.016 s | 0.97 s, 1.11 s | not measurable |
| Listing queries: mean | 59 ms | 4,340 ms, 4,831 ms | — |
| Backend cgroup peak | 97.5 MiB | 450 MiB, the limit | 450 MiB, the limit |
| Backend process RSS afterwards | 62.5 MiB | 149.8 MiB, 178.2 MiB | — |
| Backend restarts | 0 | 0 | 1, 1 |

- **Rust**: the listings that failed answered 500 after the query engine
  could not get memory for its sort within the 192 MiB pool that two
  concurrent queries share. The process was not killed and did not restart.
- **Python**: the first listings failed with the same engine error, the
  backend process then restarted, and no listing was answered. Its CPU for
  the phase cannot be read across the restart.
- **Trace queries** are barely affected: the filter leaves 32 rows to number.

This cost is in the query both backends run. It is not a difference between
them, and filter pushdown does not change it: the disturbed pushdown-off run
above showed the same failures, 12 of 60 listings. It scales with the spans
that match in the cold files a listing reads, at most the service's 20 newest
indexed files and the recent ones, so a small deployment does not see it.
Changing the query is not part of this work.

## Queries while spans arrive

Every query measurement above ran after ingestion had ended. These runs put
trace and listing queries beside live ingestion, to see what a reader gets
while the hot snapshot is being rebuilt and cold files are being produced.

The workload is the mixed cadence: 50 exporters, 300 exports each, 32 spans,
one export per exporter every 100 ms, 480,000 spans in about 30 seconds. The
query workers pause 50 ms between requests and keep running until indexing
completes.

- **Trace queries**, 8 workers: the spans of the first trace of each exporter.
- **Listing queries**, 4 workers: a service's newest root spans.

The workers also run during the 20 idle seconds before the exports start. A
trace query finds nothing then, and those answers are counted as answered.

| | Rust, new default image | Python |
| --- | ---: | ---: |
| Trace queries answered, run 1 | 5,474 of 5,475 | 4,068 of 4,068 |
| Trace queries answered, run 2 | 5,441 of 5,442 | 4,048 of 4,048 |
| Trace queries: p50 | 7.7 ms, 7.6 ms | 9.7 ms, 8.9 ms |
| Trace queries: p95 | 97 ms, 91 ms | 257 ms, 255 ms |
| Backend CPU to the end of ingestion | 14.5 s, 14.6 s | 22.5 s, 22.3 s |
| Backend cgroup peak | 94 MiB, 89 MiB | 419 MiB, 411 MiB |
| Export p95 | 9.8 ms, 7.5 ms | 12.0 ms, 9.8 ms |
| Exports refused once and retried | 36, 36 | 87, 104 |
| Listing queries answered, 1 run | 1,802 of 1,802 | 1,683 of 1,687 |
| Listing queries: p95, p99 | 18.7 ms, 1,653 ms | 24.3 ms, 226 ms |
| Backend cgroup peak, listing run | 323 MiB | 450 MiB, the limit |

All 480,000 spans were acknowledged, persisted, and indexed in every run.

**Each Rust trace run had one failed query, and Python had none.** Both
failures were a reader meeting a newer hot snapshot:

- In run 1 the snapshot file was gone. A flush had emptied the log, and the
  next snapshot request removed the file while an earlier request was about
  to read it.
- In run 2 the Parquet reader met bytes it could not decode. Another request
  had replaced the file between two of the reader's reads.

Ingestion writes the hot snapshot to one fixed path, replaces it by rename
when a request arrives after its one-second reuse period, and removes it when
its log is empty. The Python backend ran one query at a time. The Rust backend
runs them together, so a query can still be reading when the next request has
the file rewritten. The query engine opens the path again for each range it
reads, so it reads the new file with the old file's layout.

`diagnostics/snapshot-sharing-experiment.rs` reproduces this against the real
ingestion binary, with `diagnostics/snapshot-sharing-harness.patch` applied to
the cross-service test harness. In a development build, with the one-second
reuse period and new spans arriving every 10 ms, one reader failed 0 of 176
queries and eight readers failed 6 of 881. Every failure was an error. No
query returned a partial trace.

**Listing tail latency.** The Rust backend runs the four listings together,
so each has a share of the half CPU and four sorts hold memory at once: its
p99 is higher than Python's and its peak is 323 MiB. Python ran them one
after another and reached its memory limit. Four of its requests failed in
transport after ingestion ended. This is the cost in "Listing queries while
unflushed spans exist", seen while spans arrive.

**Ingestion.** The exports that ingestion refused once and the exporter
retried were fewer beside the Rust backend, and export latency was no worse.

## Real-world runs: the frontend and the SDK while spans arrive

The maintainer asked that every change be tested with queries made from the
real frontend while ingestion is processing spans at load. This section is
that test, applied to two prototypes. The prototypes were not in the working
tree when these runs were made: `diagnostics/prototype.patch` holds them,
each behind a measurement-only switch, so one image runs as the tree of that
time or as either candidate. "Current tree" in this section is that tree.
The maintainer adopted both changes afterwards, and "The adopted build"
measures the result.

**The load in this section makes listings as expensive as they get.** Every
span the exporters sent was a root span, so the Traces list matched every
span of a service, and every span of an exporter carried one start time.
"The adopted build" repeats the test with one root span per 32-span trace and
real export times, and the tree before the changes fares far better there.

**What one run is.** Split quota profile, loaded host.

- **Load**: 50 exporters, 900 exports each, 32 spans, one export per exporter
  every 100 ms. That is 1,440,000 spans in 90 seconds and 18 cold files.
- **The frontend**: Chromium, four tabs, 85 seconds. Each tab repeats what a
  person does: the services page, the Traces page as it opens (its "Has LLM
  Spans" filter is on by default), the Traces page with the filter off, one
  trace opened from that list, and the Workflow executions page. The driver
  records what each page ended up showing and every API response.
- **The real SDK**: the repository's own validator runs a real Agent, Tool,
  and Workflow composition, exports it to the same ingestion, and waits until
  Studio's APIs show it. The repository's browser proof then opens its deep
  link and checks the Agent and Workflow pages. This repeats for the whole
  run.
- **Freshness**: every two seconds a three-span trace is exported, and its
  trace route is asked every 100 ms until it returns the spans.

**The two prototypes.**

- **Listing change.** When both tiers have data, a listing removes cross-tier
  duplicates among the newest page of each tier, with the cold copy winning,
  instead of among every matching span. Both tiers are still read on every
  query.
- **Snapshot rerun.** When a query fails and ingestion has since replaced or
  removed the hot snapshot it was handed, the backend asks ingestion again
  and runs the query once more. A snapshot that cannot be registered, and one
  that is already gone, are handled the same way. A query that ran out of
  memory is not run again.

| | Current tree | Listing change only | Both changes |
| --- | ---: | ---: | ---: |
| Runs | 3 | 2 | 3 |
| Page loads completed | 219, 163, 251 | 1,161, 942 | 1,281, 1,234, 1,289 |
| API responses that were 5xx | 3 of 487, 4 of 365, 5 of 555 | 2 of 2,555, 1 of 2,072 | 0 of 2,819, 0 of 2,718, 0 of 2,839 |
| Queries run again after a snapshot change | 0, 0, 0 | 0, 0 | 2, 1, 1 |
| Traces list: p50 | 897, 1,506, 566 ms | 207, 231 ms | 187, 207, 183 ms |
| Traces list: p95 | 10,809, 12,388, 11,707 ms | 415, 511 ms | 390, 399, 398 ms |
| Traces list, default view: p50 | 949, 1,787, 937 ms | 386, 418 ms | 335, 331, 322 ms |
| Traces list, default view: p95 | 14,623, 15,833, 11,792 ms | 687, 979 ms | 665, 610, 598 ms |
| Workflow list: p50 | 597, 1,106, 593 ms | 410, 458 ms | 355, 397, 352 ms |
| Workflow list: p95 | 3,904, 4,414, 2,502 ms | 718, 933 ms | 690, 710, 625 ms |
| Trace detail: p50 | 186, 300, 254 ms | 142, 163 ms | 107, 110, 104 ms |
| Trace detail: p95 | 779, 1,459, 966 ms | 296, 377 ms | 282, 297, 219 ms |
| Services list: p50 | 367, 495, 359 ms | 268, 296 ms | 227, 228, 244 ms |
| Services list: p95 | 1,868, 3,258, 1,557 ms | 509, 688 ms | 410, 457, 474 ms |
| Pages that showed an error | 3, 4, 5 | 2, 1 | 0, 0, 0 |
| Default traces view that came back empty | 15 of 46, 11 of 35, 13 of 52 | 55 of 232, 44 of 189 | 63 of 257, 58 of 248, 60 of 258 |
| Session check on each page load: p95 | 708, 639, 379 ms | 101, 132 ms | 84, 88, 83 ms |
| Real SDK runs shown in Studio | 4 of 4, 3 of 3, 4 of 4 | 6 of 6, 6 of 6 | 6 of 6, 6 of 6, 6 of 6 |
| Real SDK run to visible in Studio | 5.8–15.3, 8.6–20.8, 5.5–14.2 s | 6.2–7.9, 4.0–8.9 s | 4.9–7.7, 5.0–7.8, 5.0–7.3 s |
| Browser proof of that run | 5.7–7.5, 7.2–9.0, 4.1–7.3 s | 3.1–3.8, 2.2–4.7 s | 2.8–3.6, 3.0–3.5, 2.7–3.3 s |
| Accepted span to readable: p50 | 1,133, 1,079, 849 ms | 480, 310 ms | 319, 280, 242 ms |
| Accepted span to readable: p95 | 2,996, 2,194, 1,979 ms | 1,194, 1,077 ms | 1,210, 1,104, 1,110 ms |
| Accepted span to readable: slowest | 3,610, 3,282, 3,411 ms | 1,384, 1,316 ms | 1,466, 1,225, 1,389 ms |
| Backend cgroup peak | 450, 450, 450 MiB | 116, 114 MiB | 113, 118, 115 MiB |
| Backend process RSS | 201, 174, 181 MiB | 73, 72 MiB | 65, 72, 70 MiB |
| Backend CPU | 43.4, 45.9, 45.1 s | 43.6, 42.1 s | 43.3, 43.3, 42.7 s |
| Ingestion CPU | 9.5, 13.6, 8.5 s | 10.4, 11.9 s | 9.2, 10.1, 9.3 s |
| Spans acknowledged | 1,439,936, 1,440,000, 1,440,000 | 1,440,000, 1,439,840 | 1,440,000, 1,440,000, 1,440,000 |
| Exports refused once and retried | 382, 458, 469 | 173, 148 | 222, 209, 175 |
| Exports that failed after retries | 2, 0, 0 | 0, 5 | 0, 0, 0 |
| Export p95 | 16.8, 57.9, 11.1 ms | 9.8, 25.0 ms | 11.5, 17.6, 10.5 ms |
| Export p99 | 83.4, 171.0, 65.5 ms | 40.8, 56.3 ms | 45.7, 51.2, 48.6 ms |

- **The listing change is what moves the experience.** Five to eight times
  as many pages loaded in the same time, the Traces list went from about 11 seconds
  at the 95th percentile to 0.4, and the backend went from its 450 MiB limit
  to about 115 MiB.
- **It also reaches ingestion.** Ingestion asks the backend to validate an
  API key every ten seconds, and exports wait for that answer. On the current
  tree the backend took 119–349 ms on average to answer while listings ran,
  and ingestion refused 382–469 exports once. With the listing change it
  took 5–51 ms, and 148–222 were refused. Every refused export was retried.
- **Freshness improved with it.** A span was readable 0.24–0.48 s after
  ingestion accepted it at the median, against 0.85–1.13 s, and within 1.5 s
  at worst, against 3.6 s. No probe went unanswered in any run.
- **The rerun removes the snapshot failures when queries are short.** With
  both changes there was no failed request in 8,376. Four queries were run
  again and answered. Without the listing change the rerun is not enough: in
  two runs with only the rerun, 1 of 434 and 8 of 418 responses failed. Six
  were memory errors, which are not run again. Two were the second read of
  the snapshot that the default Traces view makes, which the first prototype
  image did not yet cover. One slow listing met a second snapshot change
  during its rerun.
- **The real SDK path worked in every run**: 58 of 58 runs were shown in
  Studio and passed the browser proof. On the current tree a run took up to
  20.8 s to be shown, and with the listing change at most 8.9 s.
- **Failed exports.** Two exports in one current-tree run and five in one
  listing-only run were refused more times than the harness's exporter
  retries. No export failed in the three runs with both changes. Every
  acknowledged span was persisted in every run.

**Four times the load.** One run each with one export per exporter every 25
ms: 5,760,000 spans in 90 seconds and 72 cold files, which is more than the
indexer indexes in that time.

| | Current tree | Both changes |
| --- | ---: | ---: |
| Runs | 1 | 1 |
| Page loads completed | 74 | 677 |
| API responses that were 5xx | 23 of 174 | 0 of 1,493 |
| Queries run again after a snapshot change | 0 | 4 |
| Traces list: p50 | 8,303 ms | 413 ms |
| Traces list: p95 | 27,735 ms | 956 ms |
| Workflow list: p95 | 10,215 ms | 1,492 ms |
| Pages that showed an error | 23 | 0 |
| Real SDK runs shown in Studio | 4 of 4 | 6 of 6 |
| Real SDK run to visible in Studio | 8.9–14.3 s | 5.8–8.7 s |
| Accepted span to readable: p50 | 1,138 ms | 463 ms |
| Accepted span to readable: p95 | 2,619 ms | 1,076 ms |
| Accepted span to readable: slowest | 3,204 ms | 1,171 ms |
| Backend cgroup peak | 450 MiB | 126 MiB |
| Ingestion CPU | 21.4 s | 23.6 s |
| Spans acknowledged | 5,760,000 | 5,760,000 |
| Exports refused once and retried | 448 | 243 |
| Exports that failed after retries | 0 | 0 |
| Export p95 | 8.5 ms | 11.8 ms |
| Export p99 | 52.0 ms | 54.9 ms |

On the current tree the backend sat at its memory limit and the Traces and
Workflow lists failed about half the time. With both changes no request
failed. In that run the services list met one snapshot change that the
prototype's rerun does not cover: it logged the error and answered from the
index, as it does today.

**A finding neither prototype changes: the default Traces view goes empty
after a flush.** The Traces page opens with "Has LLM Spans" on. That listing
keeps a trace only if the index or the hot snapshot says it has an LLM span,
and a file that is flushed but not yet indexed is covered by neither. In
every run the default view came back empty for most loads between the first
flush, about 5 seconds in, and the first indexer cycle, about 30 seconds in:
about a quarter of all loads. The Python backend had the same rule. The
synthetic spans here all carry the start time of their exporter, so later
flushes did not empty the view again. With real start times the newest
traces are in the newest file, and the view would lose them after each flush
until the indexer reaches that file.

**Checked in the scratch copy, with the real ingestion binary:**

- The server suite passes with both switches off and with both on: 254 tests,
  including the cross-service tests.
- A differential test runs the full and the bounded listing over the same
  data, with 50 spans in both tiers, for eleven page sizes and three listing
  kinds. The pages are identical, the cold copy wins, and nothing appears
  twice.
- The concurrency experiment of "Queries while spans arrive", with the rerun
  on and the one-second reuse period: no failed query in 2,474 over three
  runs with eight readers. With snapshot reuse turned off, which no
  deployment does, 50 of about 600 still fail.

**Limits of these runs.**

- The browser and the SDK run on the host, beside the constant load, and
  share its CPUs. Run-to-run variation in export latency and ingestion CPU is
  larger than in the other sections. The maintainer's own unrelated
  containers were also started and restarted on the host while these batches
  ran.
- Two or three runs of each setting, and one at the heavier load. The Python
  backend was not run with the browser: its frontend is a separate container
  on another origin.
- The loaded services hold synthetic spans. The real SDK's spans are a small
  share of the data.
- If the same span is stored twice in one tier, that tier offers the bounded
  listing that many fewer distinct candidates, so the oldest end of a page
  can lack those spans or hold older ones in their place. The listing with
  one tier has never removed such duplicates.

## The adopted build, and the test as a repository tool

On 2026-10-04 the maintainer decided three things on the runs above: to bring
the listing change and the snapshot rerun into the tree together, to make the
real-world test a repository tool, and to have a fix for the default Traces
view prototyped and measured. This section covers the first two. The next
covers the third.

**What is in the tree.** Ingestion ADR-002 was amended first and records
both changes.

- The listing change, as prototyped.
- The snapshot rerun, extended to every place that reads the snapshot: span
  queries, the services listing, and the second read that the default Traces
  view makes. A snapshot that ingestion named and that is gone when the query
  looks now fails the query, which then asks ingestion again. Before, it was
  left out and the query answered without it.

**The earlier test on the tree's build.** One run at each load, with the
harness and the load of "Real-world runs", to check that the tree behaves as
the prototype did.

| | Prototype, both changes | Tree |
| --- | ---: | ---: |
| Standard load: page loads completed | 1,281, 1,234, 1,289 | 1,302 |
| API responses that were 5xx | 0 of 8,376 | 0 of 2,870 |
| Traces list: p95 | 390, 399, 398 ms | 365 ms |
| Backend cgroup peak | 113, 118, 115 MiB | 117 MiB |
| Accepted span to readable: p50 | 319, 280, 242 ms | 306 ms |
| Queries run again after a snapshot change | 2, 1, 1 | 5 |
| Real SDK runs shown in Studio | 18 of 18 | 6 of 6 |
| Four times the load: page loads completed | 677 | 633 |
| API responses that were 5xx | 0 of 1,493 | 0 of 1,395 |
| Traces list: p95 | 956 ms | 898 ms |
| Backend cgroup peak | 126 MiB | 126 MiB |
| Backend error lines | 1, the services listing | 0 |

**The repository tool.** `apps/studio/ingestion/benchmarks/real_world.py`
runs the same four parts: the load, the real frontend in four browser tabs,
the real SDK with both live validators, and the freshness probe. That
directory's README owns the procedure. The tool's load differs from the
earlier one in two ways, and both matter to these numbers.

- Each export is one trace with one root span, a Workflow span, and 31
  children. Before, every span was a root span.
- A trace carries the time it was exported at. Before, every span of an
  exporter carried the time its exporter started.

**Before and after the two changes, with the tool.** "Before the changes" is
the second prototype image with its switches off. Split quota profile, loaded
host. Each batch ran its builds interleaved, together with those of the next
section. The second batch did not run the build before the changes again.

| | Before the changes | Tree, first batch | Tree, second batch |
| --- | ---: | ---: | ---: |
| Runs | 3 | 3 | 3 |
| Runs that passed the harness checks | 3 of 3 | 3 of 3 | 3 of 3 |
| Page loads completed | 836, 691, 808 | 1,013, 633, 967 | 967, 949, 920 |
| API responses that were 5xx | 2 of 1,840, 3 of 1,525, 2 of 1,780 | 0 of 2,231, 0 of 1,395, 0 of 2,129 | 0 of 2,129, 0 of 2,089, 0 of 2,026 |
| Requests that failed | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Pages that showed an error | 2, 3, 2 | 0, 0, 0 | 1, 0, 0 |
| Pages that did not settle | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Page “services”: p50 ms | 303, 315, 317 | 286, 379, 277 | 290, 299, 288 |
| Page “services”: p95 ms | 679, 596, 683 | 495, 776, 510 | 507, 549, 590 |
| Page “traces, default view”: p50 ms | 521, 704, 527 | 430, 625, 444 | 486, 481, 504 |
| Page “traces, default view”: p95 ms | 1,104, 1,353, 1,098 | 877, 1,390, 891 | 821, 806, 1,004 |
| Page “traces, all”: p50 ms | 295, 413, 367 | 289, 503, 290 | 287, 288, 298 |
| Page “traces, all”: p95 ms | 802, 969, 800 | 584, 1,066, 668 | 594, 585, 606 |
| Page “trace detail”: p50 ms | 182, 225, 197 | 133, 263, 142 | 180, 192, 184 |
| Page “trace detail”: p95 ms | 411, 504, 415 | 330, 603, 385 | 315, 318, 390 |
| Page “workflows”: p50 ms | 501, 708, 580 | 467, 699, 455 | 504, 498, 518 |
| Page “workflows”: p95 ms | 1,144, 1,194, 1,097 | 817, 1,400, 926 | 822, 839, 930 |
| Default Traces view that came back empty | 5 of 168, 7 of 140, 6 of 163 | 12 of 203, 7 of 127, 6 of 195 | 7 of 194, 11 of 191, 7 of 185 |
| Default Traces view with fewer traces than the full list | 29 of 166, 20 of 135, 29 of 160 | 30 of 202, 20 of 126, 21 of 194 | 28 of 193, 34 of 190, 27 of 184 |
| Session check on each page load: p95 ms | 139, 185, 146 | 126, 145, 128 | 127, 112, 92 |
| SDK runs shown in Studio | 6 of 6, 5 of 5, 5 of 5 | 6 of 6, 4 of 4, 6 of 6 | 6 of 6, 6 of 6, 6 of 6 |
| SDK run to shown by Studio's APIs: seconds | 5.4–8.7, 5.3–9.2, 5.3–8.9 | 5.1–8.1, 8.2–10.2, 5.1–8.7 | 4.9–7.7, 6.6–8.2, 4.9–9.0 |
| SDK run found in the browser: seconds | 3.0–3.7, 3.3–4.3, 2.9–4.2 | 2.9–3.7, 4.8–6.3, 2.9–4.3 | 2.9–3.6, 2.9–3.9, 2.8–3.9 |
| Accepted trace to readable: p50 ms | 489, 617, 469 | 476, 423, 311 | 394, 382, 303 |
| Accepted trace to readable: p95 ms | 1,136, 1,372, 1,320 | 1,302, 1,506, 1,283 | 1,100, 1,204, 1,279 |
| Accepted trace to readable: slowest ms | 1,424, 1,557, 1,480 | 1,387, 1,658, 1,499 | 1,189, 1,398, 1,383 |
| Probe traces never readable | 0 of 36, 0 of 35, 0 of 35 | 0 of 34, 0 of 35, 0 of 37 | 0 of 37, 0 of 36, 0 of 37 |
| Spans acknowledged | 1,440,000, 1,440,000, 1,440,000 | 1,440,000, 1,440,000, 1,440,000 | 1,440,000, 1,440,000, 1,440,000 |
| Exports refused once and retried | 280, 256, 247 | 164, 250, 187 | 257, 131, 279 |
| Exports that failed after retries | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Export p95 ms | 16.5, 36.6, 22.5 | 10.7, 44.1, 12.2 | 19.5, 10.2, 18.0 |
| Export p99 ms | 73.2, 112.6, 68.9 | 41.4, 125.6, 58.5 | 69.2, 42.2, 67.4 |
| Backend CPU seconds | 43.4, 43.7, 43.6 | 43.3, 43.4, 43.2 | 43.2, 43.2, 43.5 |
| Ingestion CPU seconds | 9.8, 12.1, 11.1 | 9.8, 14.4, 10.2 | 10.2, 9.9, 10.5 |
| Backend peak memory MiB | 163, 167, 159 | 130, 136, 133 | 132, 130, 130 |
| Ingestion peak memory MiB | 90, 82, 78 | 81, 81, 82 | 93, 77, 78 |

Four times the load:

| | Before the changes | Tree |
| --- | ---: | ---: |
| Runs | 1 | 2 |
| Runs that passed the harness checks | 1 of 1 | 2 of 2 |
| Page loads completed | 378 | 494, 349 |
| API responses that were 5xx | 3 of 832 | 0 of 1,090, 0 of 769 |
| Pages that showed an error | 3 | 0, 0 |
| Page “traces, default view”: p50 ms | 1,252 | 984, 1,413 |
| Page “traces, default view”: p95 ms | 2,526 | 1,789, 2,387 |
| Page “traces, all”: p50 ms | 984 | 707, 1,084 |
| Page “traces, all”: p95 ms | 2,178 | 1,447, 1,870 |
| Page “workflows”: p50 ms | 1,220 | 1,201, 1,613 |
| Page “workflows”: p95 ms | 2,693 | 1,825, 2,588 |
| Default Traces view that came back empty | 35 of 76 | 35 of 100, 38 of 71 |
| Default Traces view with fewer traces than the full list | 41 of 74 | 37 of 98, 45 of 70 |
| SDK runs shown in Studio | 5 of 5 | 5 of 5, 4 of 4 |
| SDK run to shown by Studio's APIs: seconds | 6.5–10.4 | 5.3–9.6, 7.4–10.8 |
| SDK run found in the browser: seconds | 2.9–4.3 | 2.8–4.7, 4.3–6.0 |
| Accepted trace to readable: p50 ms | 514 | 478, 605 |
| Accepted trace to readable: p95 ms | 1,202 | 889, 1,274 |
| Accepted trace to readable: slowest ms | 1,792 | 1,174, 1,726 |
| Probe traces never readable | 0 of 34 | 0 of 37, 0 of 34 |
| Spans acknowledged | 5,760,000 | 5,760,000, 5,760,000 |
| Exports refused once and retried | 282 | 269, 289 |
| Exports that failed after retries | 0 | 0, 0 |
| Export p95 ms | 12.4 | 11.9, 58.0 |
| Export p99 ms | 66.9 | 72.1, 124.3 |
| Backend CPU seconds | 44.2 | 44.1, 44.0 |
| Ingestion CPU seconds | 25.3 | 24.4, 34.8 |
| Backend peak memory MiB | 246 | 189, 191 |

- **The gain is real and much smaller than with every span a root span.**
  The tree completed about 20% more page loads than the build before the
  changes in the same round: 1,013 against 836, and 967 against 808. The
  95th percentile of the Traces list fell from about 800 ms to about 600 ms.
  With every span a root span the same test had shown five to eight times as
  many page loads. A listing's old cost followed the number of spans that
  matched it, and here one span in 32 matches the Traces list.
- **No request failed on the tree.** Before the changes 7 of 5,145 responses
  were 5xx at the standard load and 3 of 832 at four times the load. All ten
  were a query reading the hot snapshot as ingestion replaced it. None was a
  memory error. On the tree none of 11,999 responses was 5xx at the standard
  load and none of 1,859 at four times the load. The backend ran 19 queries
  again at the standard load and 6 at the heavier one, and all were answered.
- **Backend memory.** The backend peaked at 130–136 MiB against 159–167 MiB,
  and at 189–191 MiB against 246 MiB at four times the load.
- **Freshness and exports are within the variation between runs.** A span was
  readable 0.30–0.48 s after ingestion accepted it at the median on the tree
  and 0.47–0.62 s before, and no probe went unanswered. Every acknowledged
  span was persisted in every run.
- **The backend's CPU quota is spent in every run.** Both builds used about
  43.5 of the 45 CPU seconds the profile allows. Four tabs, the SDK, and the
  probe ask for more than half a CPU answers, so the page loads completed
  measure how much CPU a page costs.
- **One trace detail page answered 404.** In one tree run the Traces list
  showed a trace and the trace's own page then found no spans for it. That
  was once in 3,529 trace detail loads over the 24 runs of this section and
  the next. No log line records it. It fits a flush and a snapshot rebuild
  landing between ingestion's answer and the backend's read: the query then
  reads a snapshot that no longer holds the spans and was not told of the
  file that does. Both backends have always had that window. It is not
  measured further here.

**Run-to-run variation.** In the first batch, four consecutive runs between
15:46 and 15:54 show more ingestion CPU, higher export latency, and fewer
page loads than their neighbours: the second run of each of the three builds
and the first run of the next section's first variant. The maintainer's other
containers were running on the host, and nothing in the batch explains it.
The runs are kept. The second batch has no such stretch.

## The default Traces view

The Traces page opens with "Has LLM Spans" checked. That listing takes the
newest root spans and keeps those whose trace has an LLM span according to
the metadata index or the hot snapshot. A file that is flushed but not yet
indexed is covered by neither, so its traces drop out of the default view
until the indexer reaches the file, at most about 30 seconds later, or longer
when the indexer is behind. The Python backend had the same rule.

With real export times this is visible on every flush. Every trace the
exporters send has LLM spans, so the default view and the full list should
show the same traces. On the tree the default view showed fewer than the full
list in 15% of loads at the standard load, and in 38–64% at four times the
load, where it was usually empty.

After a flush the view holds only the traces that arrived since, until those
fill a page or the indexer reaches the flushed file. At the standard load a
service refills a page in under a second and ingestion flushes about every
five seconds, which is the 15%. A deployment with little traffic flushes once
an hour, and its default view then holds almost nothing until the indexer's
next cycle, up to about 30 seconds later. That case was not run.

**Two prototypes.** `diagnostics/default-view-prototype.patch` holds them
behind measurement-only switches. Neither was in the tree when the runs of
the next two tables were made, and "Tree" in those tables is the tree before
either. The maintainer then chose the second. "The second variant in the
tree" below measures the tree's build.

- **First variant.** The listing's second read also covers the files the
  index does not hold, found by one lookup per file. It reads only the spans
  of the candidate traces: the service and the candidates' trace identifiers
  are filters the Parquet reader applies before it decodes attributes.
- **Second variant.** The first, and three additions meant to make it
  cheaper and to close the gap that remains: it asks ingestion again before
  the second read, it looks only for candidates the index has not already
  found, and it reads only spans that start at or after the oldest of their
  root spans.

| | Tree | First variant | Second variant |
| --- | ---: | ---: | ---: |
| Runs | 3 | 3 | 3 |
| Runs that passed the harness checks | 3 of 3 | 3 of 3 | 3 of 3 |
| Page loads completed | 967, 949, 920 | 849, 954, 956 | 823, 861, 881 |
| API responses that were 5xx | 0 of 2,129, 0 of 2,089, 0 of 2,026 | 0 of 1,869, 0 of 2,100, 0 of 2,106 | 0 of 1,813, 0 of 1,897, 0 of 1,941 |
| Requests that failed | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Pages that showed an error | 1, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Pages that did not settle | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Page “services”: p50 ms | 290, 299, 288 | 290, 290, 292 | 302, 292, 296 |
| Page “services”: p95 ms | 507, 549, 590 | 692, 502, 493 | 588, 503, 494 |
| Page “traces, default view”: p50 ms | 486, 481, 504 | 528, 526, 518 | 601, 618, 543 |
| Page “traces, default view”: p95 ms | 821, 806, 1,004 | 1,221, 902, 906 | 1,216, 1,097, 1,184 |
| Page “traces, all”: p50 ms | 287, 288, 298 | 283, 282, 279 | 308, 292, 288 |
| Page “traces, all”: p95 ms | 594, 585, 606 | 501, 564, 510 | 732, 695, 696 |
| Page “trace detail”: p50 ms | 180, 192, 184 | 165, 176, 180 | 200, 194, 189 |
| Page “trace detail”: p95 ms | 315, 318, 390 | 322, 320, 395 | 490, 394, 396 |
| Page “workflows”: p50 ms | 504, 498, 518 | 509, 435, 491 | 519, 510, 509 |
| Page “workflows”: p95 ms | 822, 839, 930 | 1,615, 795, 821 | 1,007, 919, 1,084 |
| Default Traces view that came back empty | 7 of 194, 11 of 191, 7 of 185 | 0 of 171, 1 of 192, 1 of 192 | 0 of 165, 0 of 173, 0 of 177 |
| Default Traces view with fewer traces than the full list | 28 of 193, 34 of 190, 27 of 184 | 0 of 170, 1 of 191, 1 of 191 | 0 of 164, 0 of 172, 0 of 176 |
| Session check on each page load: p95 ms | 127, 112, 92 | 112, 113, 103 | 114, 115, 126 |
| SDK runs shown in Studio | 6 of 6, 6 of 6, 6 of 6 | 7 of 7, 6 of 6, 6 of 6 | 5 of 5, 6 of 6, 6 of 6 |
| SDK run to shown by Studio's APIs: seconds | 4.9–7.7, 6.6–8.2, 4.9–9.0 | 3.9–7.2, 5.0–8.4, 5.2–8.3 | 6.5–9.0, 5.3–7.6, 5.1–9.2 |
| SDK run found in the browser: seconds | 2.9–3.6, 2.9–3.9, 2.8–3.9 | 2.3–3.6, 3.0–3.7, 3.0–3.7 | 3.3–4.2, 2.9–4.1, 2.9–3.8 |
| Accepted trace to readable: p50 ms | 394, 382, 303 | 265, 306, 397 | 332, 320, 301 |
| Accepted trace to readable: p95 ms | 1,100, 1,204, 1,279 | 1,174, 1,218, 1,294 | 1,291, 1,274, 1,216 |
| Accepted trace to readable: slowest ms | 1,189, 1,398, 1,383 | 1,297, 1,306, 1,476 | 1,461, 1,313, 1,387 |
| Probe traces never readable | 0 of 37, 0 of 36, 0 of 37 | 0 of 38, 0 of 36, 0 of 35 | 0 of 36, 0 of 36, 0 of 36 |
| Spans acknowledged | 1,440,000, 1,440,000, 1,440,000 | 1,440,000, 1,440,000, 1,440,000 | 1,440,000, 1,440,000, 1,440,000 |
| Exports refused once and retried | 257, 131, 279 | 169, 287, 242 | 157, 277, 228 |
| Exports that failed after retries | 0, 0, 0 | 0, 0, 0 | 0, 0, 0 |
| Export p95 ms | 19.5, 10.2, 18.0 | 22.0, 16.6, 11.1 | 30.4, 16.1, 34.3 |
| Export p99 ms | 69.2, 42.2, 67.4 | 59.3, 88.3, 57.0 | 73.2, 94.0, 75.0 |
| Backend CPU seconds | 43.2, 43.2, 43.5 | 42.4, 43.3, 43.0 | 43.4, 43.5, 43.5 |
| Ingestion CPU seconds | 10.2, 9.9, 10.5 | 10.0, 9.7, 9.3 | 12.2, 11.0, 11.1 |
| Backend peak memory MiB | 132, 130, 130 | 131, 131, 127 | 126, 128, 133 |
| Ingestion peak memory MiB | 93, 77, 78 | 79, 77, 82 | 79, 80, 78 |

Four times the load:

| | Tree | First variant | Second variant |
| --- | ---: | ---: | ---: |
| Runs | 2 | 2 | 1 |
| Runs that passed the harness checks | 2 of 2 | 2 of 2 | 1 of 1 |
| Page loads completed | 494, 349 | 439, 383 | 347 |
| API responses that were 5xx | 0 of 1,090, 0 of 769 | 0 of 969, 0 of 845 | 0 of 767 |
| Pages that showed an error | 0, 0 | 0, 0 | 0 |
| Page “traces, default view”: p50 ms | 984, 1,413 | 1,293, 1,594 | 1,527 |
| Page “traces, default view”: p95 ms | 1,789, 2,387 | 2,182, 2,590 | 2,830 |
| Page “traces, all”: p50 ms | 707, 1,084 | 874, 1,024 | 1,121 |
| Page “traces, all”: p95 ms | 1,447, 1,870 | 1,564, 1,752 | 2,218 |
| Page “workflows”: p50 ms | 1,201, 1,613 | 1,223, 1,326 | 1,297 |
| Page “workflows”: p95 ms | 1,825, 2,588 | 1,821, 2,121 | 2,926 |
| Default Traces view that came back empty | 35 of 100, 38 of 71 | 4 of 89, 1 of 78 | 0 of 71 |
| Default Traces view with fewer traces than the full list | 37 of 98, 45 of 70 | 10 of 88, 6 of 76 | 0 of 69 |
| SDK runs shown in Studio | 5 of 5, 4 of 4 | 5 of 5, 5 of 5 | 5 of 5 |
| SDK run to shown by Studio's APIs: seconds | 5.3–9.6, 7.4–10.8 | 5.0–10.2, 5.1–8.9 | 5.6–10.8 |
| SDK run found in the browser: seconds | 2.8–4.7, 4.3–6.0 | 3.6–3.9, 3.7–5.3 | 4.0–5.0 |
| Accepted trace to readable: p50 ms | 478, 605 | 578, 596 | 579 |
| Accepted trace to readable: p95 ms | 889, 1,274 | 1,117, 1,147 | 1,301 |
| Accepted trace to readable: slowest ms | 1,174, 1,726 | 1,274, 1,268 | 1,357 |
| Probe traces never readable | 0 of 37, 0 of 34 | 0 of 35, 0 of 35 | 0 of 35 |
| Spans acknowledged | 5,760,000, 5,760,000 | 5,760,000, 5,760,000 | 5,760,000 |
| Exports refused once and retried | 269, 289 | 274, 259 | 292 |
| Exports that failed after retries | 0, 0 | 0, 0 | 0 |
| Export p95 ms | 11.9, 58.0 | 15.7, 20.2 | 46.6 |
| Export p99 ms | 72.1, 124.3 | 70.5, 82.9 | 103.9 |
| Backend CPU seconds | 44.1, 44.0 | 43.8, 44.1 | 44.4 |
| Ingestion CPU seconds | 24.4, 34.8 | 25.8, 28.2 | 33.2 |
| Backend peak memory MiB | 189, 191 | 187, 191 | 192 |

- **The first variant closes the gap at the standard load.** The default view
  was shorter than the full list in 2 of 552 loads in the second batch and in
  4 of 452 in the first, against 89 of 567 and 71 of 522 on the tree.
- **Its cost is small.** The default view took about 525 ms at the median
  against about 490 ms, and the runs completed 849–956 page loads against
  920–967. Other pages, freshness, exports, and memory are within the
  variation between runs.
- **At four times the load it leaves about a tenth of loads short**: 10 of 88
  and 6 of 76, against 37 of 98 and 45 of 70. There ingestion flushes about
  every 1.3 seconds and a listing takes about as long. The second variant,
  which asks ingestion again between the listing's two reads, has none
  short, which fits a flush landing between them. That was not checked
  directly.
- **The second variant closes that too.** No default view was short in 512
  loads at the standard load or in 69 at four times the load. In this batch
  it completed 823–881 page loads against 920–967, the default view took
  540–620 ms at the median, and ingestion used about 10% more CPU. The two
  later batches do not bear out the ingestion figure and put the page-load
  cost lower. Ingestion's CPU is the same with and without the variant
  there, so the host was most likely slower during this batch's three runs
  of it. The three additions were measured together, so these runs do not
  say what each would do alone.

**Checked in the scratch copy.** The server suite passes with the switches
off, with the first variant on, and with both on: 259 tests, including the
cross-service tests against the real ingestion binary. One test puts an LLM
span in an unindexed file and asserts that the listing omits its trace with
the switches off and returns it with either variant.

### The second variant in the tree

On 2026-10-04 the maintainer chose the second variant. Ingestion ADR-002 was
amended first and owns the decision. The tree has no switch: the earlier
read of the hot snapshot alone is gone. Two more batches ran the tree's
build. In both, "Before this change" is the image built from the tree before
it, which the tables above call the tree.

**Fourth batch: the two builds alternating on a quiet host.** Ingestion used
8.6–9.4 CPU seconds in every run.

| | Before this change | Tree |
| --- | ---: | ---: |
| Runs | 4 | 4 |
| Runs that passed the harness checks | 4 of 4 | 4 of 4 |
| Page loads completed | 1,103, 1,028, 1,083, 1,124 | 1,061, 1,026, 1,027, 961 |
| API responses that were 5xx | 0 of 2,427, 0 of 2,264, 0 of 2,385, 0 of 2,476 | 0 of 2,339, 0 of 2,260, 0 of 2,263, 0 of 2,115 |
| Requests that failed | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Pages that showed an error | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Pages that did not settle | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Page “services”: p50 ms | 276, 283, 282, 221 | 276, 274, 274, 304 |
| Page “services”: p95 ms | 485, 511, 481, 437 | 462, 575, 495, 484 |
| Page “traces, default view”: p50 ms | 416, 407, 407, 409 | 491, 496, 496, 556 |
| Page “traces, default view”: p95 ms | 713, 805, 727, 791 | 799, 879, 910, 900 |
| Page “traces, all”: p50 ms | 264, 280, 273, 270 | 218, 277, 225, 206 |
| Page “traces, all”: p95 ms | 500, 583, 505, 486 | 492, 507, 486, 483 |
| Page “trace detail”: p50 ms | 159, 156, 132, 127 | 171, 131, 133, 116 |
| Page “trace detail”: p95 ms | 311, 383, 311, 323 | 313, 314, 322, 303 |
| Page “workflows”: p50 ms | 415, 422, 423, 405 | 416, 424, 427, 501 |
| Page “workflows”: p95 ms | 743, 803, 709, 803 | 730, 789, 777, 811 |
| Default Traces view that came back empty | 8 of 221, 7 of 207, 5 of 218, 7 of 225 | 0 of 214, 0 of 206, 0 of 207, 0 of 193 |
| Default Traces view with fewer traces than the full list | 30 of 221, 28 of 205, 29 of 217, 39 of 224 | 0 of 211, 0 of 205, 0 of 205, 0 of 192 |
| Session check on each page load: p95 ms | 92, 126, 94, 98 | 91, 98, 96, 89 |
| SDK runs shown in Studio | 6 of 6, 7 of 7, 6 of 6, 6 of 6 | 6 of 6, 6 of 6, 6 of 6, 6 of 6 |
| SDK run to shown by Studio's APIs: seconds | 4.6–6.9, 4.6–7.7, 4.6–8.3, 4.7–7.1 | 4.5–7.4, 4.8–8.1, 4.7–7.5, 4.6–7.5 |
| SDK run found in the browser: seconds | 2.6–3.4, 2.6–3.3, 2.8–3.5, 2.8–3.4 | 2.7–3.7, 2.8–3.3, 2.6–3.5, 2.5–3.8 |
| Accepted trace to readable: p50 ms | 336, 307, 198, 302 | 371, 461, 285, 432 |
| Accepted trace to readable: p95 ms | 1,276, 1,303, 1,164, 1,192 | 1,202, 1,399, 1,258, 1,178 |
| Accepted trace to readable: slowest ms | 1,498, 1,490, 1,303, 1,394 | 1,381, 1,589, 1,272, 1,430 |
| Probe traces never readable | 0 of 36, 0 of 35, 0 of 39, 0 of 37 | 0 of 36, 0 of 35, 0 of 37, 0 of 34 |
| Spans acknowledged | 1,440,000, 1,440,000, 1,440,000, 1,440,000 | 1,440,000, 1,440,000, 1,440,000, 1,440,000 |
| Exports refused once and retried | 109, 96, 163, 159 | 176, 234, 181, 168 |
| Exports that failed after retries | 0, 0, 0, 0 | 0, 0, 0, 0 |
| Export p95 ms | 8.8, 12.6, 11.3, 7.2 | 7.4, 18.1, 12.1, 15.9 |
| Export p99 ms | 52.4, 45.9, 49.7, 34.1 | 45.3, 85.8, 42.3, 51.6 |
| Backend CPU seconds | 43.0, 43.0, 43.0, 43.1 | 43.1, 43.1, 43.0, 42.1 |
| Ingestion CPU seconds | 8.9, 9.4, 9.2, 8.6 | 8.7, 9.2, 9.2, 9.2 |
| Backend peak memory MiB | 129, 134, 135, 131 | 126, 129, 128, 130 |
| Ingestion peak memory MiB | 91, 81, 79, 77 | 81, 76, 80, 81 |

Four times the load:

| | Before this change | Tree |
| --- | ---: | ---: |
| Runs | 2 | 2 |
| Runs that passed the harness checks | 2 of 2 | 2 of 2 |
| Page loads completed | 503, 504 | 495, 425 |
| API responses that were 5xx | 0 of 1,107, 0 of 1,114 | 0 of 1,093, 0 of 937 |
| Pages that showed an error | 0, 0 | 0, 0 |
| Page “traces, default view”: p50 ms | 1,006, 919 | 1,050, 1,194 |
| Page “traces, default view”: p95 ms | 1,820, 1,615 | 1,900, 2,762 |
| Page “traces, all”: p50 ms | 764, 702 | 796, 773 |
| Page “traces, all”: p95 ms | 1,413, 1,302 | 1,406, 1,320 |
| Page “workflows”: p50 ms | 1,104, 1,208 | 1,114, 1,308 |
| Page “workflows”: p95 ms | 1,709, 1,998 | 1,823, 2,790 |
| Default Traces view that came back empty | 35 of 101, 30 of 103 | 0 of 100, 0 of 86 |
| Default Traces view with fewer traces than the full list | 45 of 101, 39 of 100 | 0 of 98, 0 of 85 |
| SDK runs shown in Studio | 5 of 5, 5 of 5 | 5 of 5, 6 of 6 |
| SDK run to shown by Studio's APIs: seconds | 4.9–8.5, 5.3–8.9 | 5.4–9.4, 4.1–8.9 |
| SDK run found in the browser: seconds | 3.1–4.5, 2.8–4.2 | 3.0–4.1, 2.5–4.7 |
| Accepted trace to readable: p50 ms | 421, 467 | 428, 475 |
| Accepted trace to readable: p95 ms | 1,224, 1,106 | 1,211, 1,010 |
| Accepted trace to readable: slowest ms | 1,496, 1,300 | 1,404, 1,199 |
| Probe traces never readable | 0 of 37, 0 of 36 | 0 of 36, 0 of 36 |
| Spans acknowledged | 5,760,000, 5,760,000 | 5,760,000, 5,760,000 |
| Exports refused once and retried | 314, 291 | 284, 291 |
| Exports that failed after retries | 0, 0 | 0, 0 |
| Export p95 ms | 10.9, 9.8 | 11.3, 10.1 |
| Export p99 ms | 68.5, 66.2 | 71.3, 60.0 |
| Backend CPU seconds | 43.9, 43.9 | 44.0, 41.9 |
| Ingestion CPU seconds | 23.4, 23.4 | 23.6, 23.4 |
| Backend peak memory MiB | 188, 188 | 183, 186 |

**Third batch: with the prototype image beside them.** Four of its nine
standard runs ran while the host was slower: the second and third of the
tree, and the third of each other build. Ingestion used 11–13 CPU seconds in
those and 9.5–9.9 in the others.

| | Before this change | Prototype, second variant | Tree |
| --- | ---: | ---: | ---: |
| Runs | 3 | 3 | 3 |
| Page loads completed | 931, 958, 792 | 955, 958, 857 | 945, 779, 673 |
| API responses that were 5xx | 0 of 2,051, 0 of 2,112, 0 of 1,746 | 0 of 2,103, 0 of 2,112, 0 of 1,889 | 0 of 2,081, 0 of 1,719, 0 of 1,483 |
| Page “traces, default view”: p50 ms | 419, 481, 552 | 573, 502, 587 | 499, 681, 745 |
| Page “traces, default view”: p95 ms | 989, 823, 1,204 | 916, 910, 1,109 | 1,023, 1,229, 1,516 |
| Default Traces view that came back empty | 6 of 187, 5 of 193, 6 of 160 | 0 of 192, 0 of 193, 0 of 173 | 0 of 190, 0 of 158, 0 of 136 |
| Default Traces view with fewer traces than the full list | 32 of 186, 33 of 191, 23 of 158 | 0 of 191, 0 of 191, 0 of 171 | 0 of 189, 0 of 155, 0 of 134 |
| Accepted trace to readable: p50 ms | 361, 395, 407 | 449, 287, 388 | 477, 575, 326 |
| Accepted trace to readable: p95 ms | 1,111, 1,182, 1,218 | 1,197, 1,385, 1,271 | 1,397, 1,405, 1,412 |
| Accepted trace to readable: slowest ms | 1,282, 1,389, 1,444 | 1,294, 1,502, 1,397 | 1,695, 1,874, 1,592 |
| Probe traces never readable | 0 of 37, 0 of 35, 0 of 35 | 0 of 35, 0 of 36, 0 of 36 | 0 of 35, 0 of 34, 0 of 36 |
| Exports refused once and retried | 207, 144, 157 | 253, 159, 176 | 169, 238, 136 |
| Export p95 ms | 18.3, 10.9, 24.8 | 15.0, 16.2, 20.6 | 10.9, 19.0, 30.3 |
| Ingestion CPU seconds | 9.5, 9.5, 11.6 | 9.9, 9.7, 11.1 | 9.6, 11.6, 12.7 |

Four times the load:

| | Before this change | Prototype, second variant | Tree |
| --- | ---: | ---: | ---: |
| Runs | 1 | 1 | 1 |
| Page loads completed | 448 | 431 | 473 |
| API responses that were 5xx | 0 of 988 | 0 of 951 | 0 of 1,041 |
| Page “traces, default view”: p50 ms | 994 | 1,299 | 1,014 |
| Page “traces, default view”: p95 ms | 2,181 | 2,309 | 1,864 |
| Default Traces view that came back empty | 43 of 91 | 0 of 87 | 0 of 95 |
| Default Traces view with fewer traces than the full list | 47 of 90 | 0 of 86 | 0 of 95 |
| Accepted trace to readable: p50 ms | 411 | 469 | 532 |
| Accepted trace to readable: p95 ms | 787 | 1,019 | 1,116 |
| Accepted trace to readable: slowest ms | 1,094 | 1,444 | 1,269 |
| Probe traces never readable | 0 of 37 | 0 of 36 | 0 of 35 |
| Exports refused once and retried | 189 | 285 | 293 |
| Export p95 ms | 23.7 | 30.7 | 15.9 |
| Ingestion CPU seconds | 26.6 | 26.1 | 24.7 |

- **No default view was short on the tree**: none of 1,291 loads at the
  standard load and none of 278 at four times the load, over both batches.
  Before the change 214 of 1,402 and 131 of 291 were.
- **It costs about 6% of page loads.** In the four alternating pairs the
  tree completed 961–1,061 page loads and the build before it 1,028–1,124.
  At four times the load the tree completed 495 and 425 against 503 and 504.
  The backend spends its whole CPU quota in every run, so this is CPU that
  the default view now uses to read the unindexed files.
- **The default view is about 90 ms slower at the median**: about 500 ms
  against about 410 ms, and 800–910 ms against 713–805 ms at the 95th
  percentile. The other pages are unchanged.
- **Ingestion's CPU is unchanged**: 8.7–9.2 s against 8.6–9.4 s, and 23.4–23.6
  s against 23.4 s at four times the load. The 10% that the second batch
  showed for the prototype did not recur. How often ingestion built a
  snapshot was not counted in any run.
- **A span is readable a little later.** In the fourth batch a span was
  readable 0.29–0.46 s after it was accepted at the median on the tree,
  against 0.20–0.34 s, with the same 95th percentile and slowest span. In the
  third batch the slowest span took 1.6–1.9 s on the tree against 1.3–1.4 s,
  and the 95th percentile 1.4 s against 1.1–1.2 s. Two of the tree's three
  runs there were on the slower host, but its quiet run shows it too. At
  four times the load the fourth batch shows no difference, and the third
  batch's single runs show a 95th percentile of 1.1 s against 0.8 s. No
  probe went unanswered.
- **Exports.** In the fourth batch ingestion refused 168–234 exports once on
  the tree against 96–163. The third batch shows no such difference: 169,
  238, and 136 against 207, 144, and 157. At four times the load it was 284
  and 291 against 314 and 291 in the fourth batch, and 293 against 189 in
  the third. Every refused export was retried and none failed, and every
  acknowledged span was persisted.
- **No request failed on the tree**: none of 14,260 responses at the standard
  load and none of 3,071 at four times the load. The backend ran 36 queries
  again after a snapshot change and all were answered. All 56 SDK runs were
  shown in Studio.
- **The tree behaves as the prototype did.** In the third batch's first
  round, on a quiet host, the build before the change completed 931 page
  loads, the prototype 955, and the tree 945, and neither of the two had a
  short default view.

**Reading page loads across runs.** Ingestion does the same work in every
run at one load, so its CPU seconds show how fast the host was during the
run. Over the 48 runs made with the tool, page loads fall as ingestion's CPU
seconds rise, in every build: at the standard load the builds with the two
adopted changes completed 849–1,124 page loads when ingestion used under
10.6 CPU seconds, and 606–881 when it used 11 or more. A build is therefore
compared with the neighbouring runs of the other build, and not with a run
from a slower stretch.

## The indexer retry and the trace query change

Two fixes followed: the indexer tries a file again when it failed on I/O or
on the index write, and a span query asks ingestion after its index lookup
and runs a trace query again when it found nothing under a changed snapshot.
Neither is expected to change what a healthy run measures, so they were run
together as a check, alternating with the build before them. Runs
`tool-tree2-standard-8` to `-10`, `tool-tree3-standard-1` to `-3`, and one
heavy run of each.

| | Before the two fixes | Tree |
| --- | ---: | ---: |
| Page loads completed | 902, 861, 834 | 819, 878, 902 |
| API responses that were 4xx or 5xx | 0 of 5,723 | 0 of 5,723 |
| Trace detail: p95 | 383, 404, 413 ms | 401, 391, 399 ms |
| Default Traces view short | 0 of 518 | 0 of 519 |
| Accepted trace to readable: p50 | 387, 503, 344 ms | 393, 429, 307 ms |
| Four times the load: page loads | 427 | 418 |

No difference is visible. No trace query found nothing under a changed
snapshot in these runs, so the new rerun did not fire: that case appeared
once in 7,410 trace detail loads before, and these runs cannot show that it
is gone. A test with a stand-in ingestion covers the decision.

## The two pages that read a service's history

Two requests read everything a service ever sent: the Agent listing reads
every Agent span of the service to return one page, and execution resolution
reads every executable span to find one. Neither is changed. They were
measured with the repository tool's `--history-pages` option, which adds the
Agents page and one execution link to each tab's round, on the tree after
the changes above. Two runs at each load.

| | Standard load, 18 cold files | Four times the load, 72 cold files |
| --- | ---: | ---: |
| Agents page: p50 | 956, 867 ms | 2,763, 2,314 ms |
| Agents page: p95 | 2,741, 2,479 ms | 4,289, 3,810 ms |
| Agent listing requests that were 5xx | 1 of 80, 4 of 84 | 23 of 40, 21 of 38 |
| Execution link: p50 | 504, 420 ms | 1,204, 1,101 ms |
| Execution link: p95 | 1,588, 894 ms | 1,979, 1,588 ms |
| Execution resolution requests that were 5xx | 0 of 80, 0 of 83 | 0 of 39, 0 of 38 |
| Backend peak memory | 312, 305 MiB | 317, 331 MiB |

- Every failed Agent listing ran out of memory while sorting. The synthetic
  load has five Agent spans in every 32-span trace, which is more than an
  application's traces would have.
- The exporters' Agent spans carry no Agent contract attributes, so the
  listing answered 409 once it had read them. The read is what was measured.
- The other pages are slower in these runs than in the ones above, because
  these two pages take the backend's CPU and memory. No comparison with
  those runs is intended.

## Image and container count

| | Python release | Rust |
| --- | ---: | ---: |
| Images a Studio release publishes | 3 | 2 |
| Backend image, compressed | 157.9 MB | 65.1 MB, with the UI |
| Frontend image, compressed | 27.5 MB | none |
| Backend binary | — | 95.5 MB |
| Frontend container memory | about 10 MiB | none |

The frontend container's memory was measured in the first comparison.

## Validation on the same tree

Run on 2026-10-03 and 2026-10-04, before the measured batch.

- Studio's full test script passes: backend format and lint, 223 server tests
  and 121 evidence tests, 40 ingestion tests, 257 frontend tests with lint and
  build, 31 contract tests, and the OpenAPI document check.
- The backend suite also passes on Linux in a container limited to four CPUs.
- The Rust generators reproduce the three generated projection files of the
  published revision byte for byte, and the exported OpenAPI document has no
  difference from the published one beyond the accepted ones.
- Telemetry contract 3: the fixtures regenerate to a tree identical to the
  published one, the validator passes, and the producer conformance tests
  (246) and the evidence crate pass.
- Python SDK 0.69.0: Ruff, 471 tests, ty, the Griffe public-surface check, the
  package build, and Twine all pass.
- Deployment distributions: the validators, the end-to-end harness checks,
  and the Caddy configuration check pass. Both archives export from a
  committed copy of the tree and are identical across two exports.
- The distribution smoke test passes on the VM/Caddy distribution with locally
  built arm64 images and the published SDK, including both browser proofs.
- The website assembles, type-checks, builds, and passes its build and
  documentation checks. Its dependency audit reports three high-severity
  advisories in the published lockfile, which this work does not change.
- The repository, runtime, deployment, and license validators and the 163
  tooling tests pass.

Run again on 2026-10-04 on the tree with the three adopted changes and the
repository tool:

- Studio's full test script passes: backend format and lint, 264 server tests
  and 121 evidence tests, 40 ingestion tests, 291 frontend tests with lint and
  build, 38 contract tests, and the OpenAPI document check.
- The repository, runtime, and deployment validators, the 164 tooling tests,
  and the benchmark directory's 6 tests pass.
- The new listing test fails when each tier offers its oldest spans instead
  of its newest, and when the hot copy of a span wins. The new cross-service
  test, eight concurrent readers against the real ingestion at the
  deployment's one-second snapshot reuse, fails in three of three runs with
  the rerun disabled and passes in six of six with it.
- The tests of the default Traces view fail when the unindexed files are not
  read and when the start time bound is taken from the newest root span
  instead of the oldest. One of them runs against the real ingestion: it
  lists a trace before its flush and after it, with no indexer running.

## Limits

- One host: Apple Silicon macOS with OrbStack, 12 CPUs, and 15 unrelated
  containers running. Run counts are small. Ranges are shown wherever more
  than one run exists.
- The harness's workload queries are service discovery. The filtered-query
  phase adds trace and listing queries after ingestion, on a quiet backend.
  Only "Listing queries while unflushed spans exist" measures them with a hot
  snapshot present. Evidence assembly and evaluation paths are not measured.
- The trace queries began about 27 seconds after the last flush. Ingestion
  reports a flushed file as recent for 120 seconds, so each trace query read
  the 16 recent files and not only the one that holds its trace.
- The data is synthetic: three services, spans without parents, and traces of
  32 spans that each sit in one cold file. With spans without parents every
  span is a root span, which is the most expensive data for a Traces listing.
  Only "The adopted build" and "The default Traces view" use traces with one
  root span and real export times.
- In those two sections a trace is one root span with flat children, and
  every trace has LLM spans. Only the SDK's runs have real nesting, events,
  and Store state. Four browser tabs are one person moving quickly.
- Docker's sampled memory is a container working-set figure, not process RSS.
  Both are reported.
- The base Compose file sets glibc allocator variables for the backend
  service. They apply to both backends.
- The amd64 image builds under emulation and its binary runs. It was not
  measured.
- The CLI browser sign-in, work package 10, was added after this batch. It
  adds routes and one table and does not change a measured path.

## Reproduction

- [Summary](summary.json) holds the metrics and medians of the first 29
  runs. [Decision runs](summary-decision-runs.json) holds the runs named
  `confirm`, `hot`, and `live`. [Real-world runs](summary-realworld.json)
  holds the runs named `rw`. [Tool runs](summary-tool.json) holds the 48
  runs made with the repository tool, with each run's time, image
  identities, and load.
- [Provenance](provenance.json) records the source state, the commit that
  holds it, image identities, host, and conditions.
- The raw result of each run and the services' logs are not in the
  repository. They stay with whoever made the runs, in a `results/`
  directory here that Git ignores. The summaries hold every figure this
  document reports. The file names below identify runs in the summaries.
- Run names are
  `load-<variant>-<shape>-<repetition>`. Variants ending in `shared` are the
  single CPU profile, and `rust-pushdown` is the Rust image with filter
  pushdown on. The `saturation` shape is the index-completion workload, and
  `filtered` is that workload followed by the filtered queries.
- The runs of 2026-10-04 are `confirm-<variant>-filtered-<repetition>` and
  `hot-<variant>-filtered-hot-<repetition>`. The variant `rust-default` is the
  image built after the decision, with pushdown on and no variable. The shape
  `filtered-hot` is `filtered` with 32 spans exported after indexing completes
  and left unflushed, and 20 listing queries. `overlay-rust-pushdown.yaml`
  sets the removed variable, which only the earlier image reads.
- The real-world runs are `rw-<variant>-realworld-<repetition>` and
  `rw-<variant>-realworld-heavy-1`. `proto` and `proto2` are the first and
  second prototype images, and the suffix names the switches that were on:
  `base` none, `dedupe` the listing change, `retry` the rerun, `both` both.
  Only `proto2` has the rerun cover the default Traces view's second read.
  `diagnostics/realworld/` holds the browser driver, the runner that starts
  it and the SDK proof, and the scripts that made the tables. They are the
  first form of what is now the repository tool, and
  `diagnostics/prototype.patch` is the first form of the two changes that
  are now in the tree.
  `summary-realworld.json` holds every run's figures.
- The runs of "The adopted build" and "The default Traces view" are
  `tool-<variant>-<rate>-<repetition>`, made with
  `apps/studio/ingestion/benchmarks/real_world.py`. `before` is the second prototype image with its switches off,
  `adopted` the image built from the tree with the first two changes,
  `viewfix` and `viewfix2` the first and second variants, and `tree2` the
  image built from the tree with the second variant adopted. `rate` is
  `standard` or `heavy`, the latter with `--export-interval-ms 25`. The first
  batch is repetitions 1 to 3 of `before`, `adopted`, and `viewfix`, and
  `heavy` repetition 1 of each. The second is `adopted` 4 to 6, `viewfix` 4
  to 6, `viewfix2` 1 to 3, and their next `heavy` run. The third is
  `adopted` 7 to 9, `viewfix2` 4 to 6, `tree2` 1 to 3, and their next
  `heavy` run. The fourth is `adopted` 10 to 13, `tree2` 4 to 7, and two
  `heavy` runs of each. `diagnostics/real-world-tool/` holds the batch runner and
  the overlays, and `real_world_report.py` prints the tables from these
  files. `rw-rust-adopted-realworld-1` and `-heavy-1` are the tree's image on
  the earlier harness.
- The runs of "Queries while spans arrive" are
  `live-<variant>-live-trace-<repetition>` and `live-<variant>-live-list-1`.
  `diagnostics/batch-live.sh` is their batch, and the harness patch holds the
  `--workload-query` option they use.
- `diagnostics/` holds the harness patch, the completion observer, the run
  driver, the batch scripts, the Compose overlays, and the aggregation
  scripts. The driver and batch scripts keep their original session paths;
  adapt them when replaying.
- Apply `diagnostics/benchmark.patch` to a copy of
  `apps/studio/ingestion/benchmarks`. Build the three images before measuring,
  and keep builds and test suites out of measurement rounds.
