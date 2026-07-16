# Ingestion authorization benchmark

`auth_path_benchmark.py` exercises the real canonical Studio backend and Rust
OTLP ingestion service with a benchmark-only Compose overlay. The overlay
allocates half a CPU to each service and 800 MiB of combined container memory,
approximating the supported one-vCPU/1GB host after OS overhead.

Run from `apps/studio` through the backend's locked Python environment:

```bash
uv run --project backend python ingestion/benchmarks/auth_path_benchmark.py \
  --output /tmp/junjo-auth-benchmark.json
```

The harness defaults to local ports `27154` and `27155`; use `--backend-port`
and `--ingestion-port` if either is occupied. It uses only synthetic
credentials, creates a temporary data mount, starts backend and ingestion from
the canonical `compose.yaml`, drives OTLP and authenticated query traffic,
measures key revocation, then removes its containers, volumes, and data.
Revocation results distinguish the last successfully accepted export from the
first rejection response; only the former measures the authorization window,
while the latter also includes the authoritative invalid lookup and response
latency after expiry.

Use `--cache-ttl-seconds 0` for the no-cache comparison and `--skip-build` when
the current images have already been built. Other flags expose the bounded
cache, concurrency, pending-request, timeout, exporter, batch-size, and query
dimensions recorded in Studio ADR-009. Cold-path `UNAVAILABLE` responses are
retried with bounded exponential backoff and deterministic per-exporter jitter
by default, matching OTLP exporter ownership of retry buffering without making
runs irreproducible; use `--max-retries 0` to inspect raw saturation.

The harness exits nonzero unless every logical export and query succeeds and
the warmed deleted key is rejected within the measurement deadline. Attempt
codes and final logical outcomes are reported separately so retries cannot
mask dropped benchmark work.

`--key-topology shared` reuses one credential across exporters, while
`--key-topology distinct` creates one real Studio API key per exporter.
`--timing synchronized` aligns exporter schedules; `--timing staggered`
distributes their first export across one interval. `--export-interval-ms` is a
start-to-start cadence by default, so a healthy candidate is compared at the
same offered rate rather than being given less work when an earlier request is
slower. `--cadence-mode after-completion` models exporters that wait one full
interval after each completed export; the matrix uses both modes because a TTL
equal to the export interval behaves differently across them.

This is an engineering comparison harness, not a universal capacity claim.
Record the commit, host architecture, Docker resources, exact arguments, and
raw JSON with every accepted result.

Run the repository-owned candidate matrix after building the current images:

```bash
uv run --project backend python ingestion/benchmarks/auth_path_matrix.py \
  --output ../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_MATRIX.json
```

The matrix varies TTL, cache capacity, validation concurrency, pending-request
capacity, deadline under a controlled 1.25-second backend delay, exporter
count, key topology, synchronization, and span batch size. Every scenario uses
the counting proxy and the same aggregate one-vCPU allocation. The 1-second
deadline scenario is an expected fail-fast result; all other candidates must
complete every logical export and query.

## Historical transport baselines

The committed `historical-no-cache.patch` is benchmark evidence only. To
reproduce the two historical transport baselines without adding a production
fallback, create detached worktrees at the exact reviewed commit:

```bash
git worktree add --detach /tmp/junjo-auth-historical <reviewed-sha>
git worktree add --detach /tmp/junjo-auth-fresh-no-cache <reviewed-sha>
git -C /tmp/junjo-auth-fresh-no-cache apply \
  "$PWD/apps/studio/ingestion/benchmarks/historical-no-cache.patch"
```

Run this harness from the current checkout with
`JUNJO_BENCHMARK_COMPOSE_ROOT` pointing at the applicable worktree's
`apps/studio` directory. Use `--implementation-label historical-600-fresh`
and `--cache-ttl-seconds 600` for the unmodified worktree. Use
`--implementation-label no-cache-fresh` and `--cache-ttl-seconds 0` for the
patched worktree. Both runs should use `--skip-revocation`; the historical
600-second behavior is measured only as a warm-path performance baseline and
is not restored to the active source tree.
