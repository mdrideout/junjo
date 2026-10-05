# Ingestion authorization benchmark

`auth_path_benchmark.py` exercises the real canonical Studio backend and Rust
OTLP ingestion service with a benchmark-only Compose overlay. The overlay
allocates half a CPU to each service and 800 MiB of combined container memory,
approximating the supported one-vCPU/1GB host after OS overhead.

The harness has its own locked Python project in this directory. Run from
`apps/studio/ingestion/benchmarks`:

```bash
uv run python auth_path_benchmark.py \
  --verify-delivery --wal-probe-spans 0 --output /tmp/junjo-auth-benchmark.json
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

Use `--first-user-path` and `--api-keys-path` when the backend under test
serves those two setup routes somewhere else. They are recorded under
`setup_paths` and are not part of the compared workload, so results from
backends with different setup routes remain comparable.

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

Delivery verification is enabled by default. Each logical export gets distinct
span identities; retries reuse those identities. After the measured workload,
both disposable services stop before the harness reads canonical WAL streams
and cold Parquet. The report separates offered, fully acknowledged, uniquely
persisted, duplicate and missing spans. Hot snapshots do not count as another
copy of canonical data. Partial-success responses with rejected spans fail the
logical export. Missing acknowledged spans or failed ingestion shutdown fail
the run even if apparent throughput is high.

Use `--no-verify-delivery` only to reproduce the older authorization workload
that reused identities. Do not compare its absolute throughput directly with
the identified workload: generating distinct IDs adds client-side work. The
optional legacy WAL mtime probe is diagnostic; file timestamps cannot prove
the fate of every span or host-failure durability. Abrupt termination may lose
buffered telemetry under [ADR-001](../adr/001-segmented-wal-architecture.md).

## Comparing production candidates

Build baseline and candidate production images before running measurements.
Set `JUNJO_BENCHMARK_COMPOSE_OVERLAY` to a Compose file selecting those images,
use `--skip-build`, and set `JUNJO_BENCHMARK_PROJECT_NAME` to an isolated project
name. The harness records actual image IDs, CPU affinity, CPU/memory/swap limits, cgroup CPU
usage and peak memory, sampled resources, OOM state and restarts. Never point
this harness at an existing deployment's data directory.

Alternate baseline/candidate order across repeated runs. Use identical
arguments and limits for paced ingestion with concurrent queries, unpaced
capacity, serial exporters, sparse requests, full batches and cold rollover.
Paced throughput is limited by offered traffic; report latency and actual
completed query counts alongside it. Docker memory samples are container
working-set measurements, not precise process RSS. Cgroup CPU differences also
include the common measurement overhead and any query tail.

`compare_results.py` requires verified delivery and rejects failed runs and
mismatched workloads, CPU affinity or actual resource limits. It reports medians
and ranges, CPU per acknowledged span,
memory and latency changes. Supply explicit throughput/query tolerances from
the applicable accepted performance decision; the script defines no new
product thresholds. Compare to the immediate baseline and retain accepted
release evidence separately to prevent gradual regressions. A passing numeric
comparison does not waive CPU, memory or tail-latency review.

Keep builds and test suites out of measurement rounds. Use
`--recovery-seconds` for an explicit idle observation period after measured
work; the report includes those samples and separate cgroup readings. This
option does not change any production timer. Retain contaminated runs as
diagnostics and rerun the affected comparison.

When unchanged-versus-unchanged controls vary beyond the acceptance margin,
report the comparison as inconclusive and use a quieter measurement host.
CPU-affinity experiments belong in a separate overlay and separate comparison;
they do not replace the original resource-profile results. With `--output`,
the harness also saves service logs beside the JSON before removing its stack.
Both services log at level `warn`.

The older `e2e_test_apps/orchestration/benchmark.py` headline counts generated
spans, which can exceed delivered spans when its exporter queue drops work.
That headline alone is not performance acceptance evidence.

Run benchmark correctness checks from this directory:

```bash
uv run pytest -q test_delivery.py
```

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

See the [September 2026 ownership and notification review](../../../../docs/roadmaps/evidence/studio-store-ingestion-2026-09-06/README.md)
for measured candidates, rejected experiments and remaining acceptance limits.

Run the repository-owned candidate matrix after building the current images:

```bash
uv run python auth_path_matrix.py \
  --output ../../../../docs/roadmaps/STUDIO_INGESTION_API_KEY_AUTHORIZATION_MATRIX.json
```

The matrix varies TTL, cache capacity, validation concurrency, pending-request
capacity, deadline under a controlled 1.25-second backend delay, exporter
count, key topology, synchronization, and span batch size. Every scenario uses
the counting proxy and the same aggregate one-vCPU allocation. The 1-second
deadline scenario is an expected fail-fast result; all other candidates must
complete every logical export and query.

The counting proxy is `auth_backend_proxy.py`. Compose builds its image from
the `Dockerfile` in this directory, which generates the proxy's gRPC stubs
from `proto/auth.proto`. The stubs are not checked in.

## Real-world runs

A change to the query path, the backend, or ingestion is measured from where
a person and an application use Studio, while ingestion processes spans. The
root `AGENTS.md` states that requirement. This section owns the procedure.

Queries sent to the API, and queries sent after ingestion has finished, do
not show what Studio's pages do while spans arrive. On a live deployment
every query also reads the hot snapshot of unflushed spans, concurrent pages
share the backend's query memory, and a busy backend slows the API key
validation that ingestion asks it for.

`real_world.py` runs the harness with four things at once:

- **Load.** The exporters send Studio-shaped traces (`--span-shape studio`):
  a Workflow root span with every other span as its child, two in six of them
  LLM spans, written to three services and stamped with the time of export.
  By default 50 exporters each send one 32-span trace every 100 ms for 90
  seconds, which offers 16,000 spans a second and 1,440,000 in all.
- **The real frontend.** `frontend/e2e/live-load.mjs` signs in and drives four
  browser tabs through the pages a person uses: the services page, the Traces
  page as it opens with "Has LLM Spans" checked, the Traces page with every
  trace, one trace's detail, and the Workflow executions page. It records
  what each page showed and how long that took, and the status and time of
  every API response.
- **The real SDK.** `tooling/scripts/validate_agent_studio_e2e.py` runs a
  deterministic Agent composition with the Python SDK, exports its spans to
  the same ingestion service, and checks Studio's APIs for the run. The
  frontend's `test:e2e:agent-live` proof then finds the run in a browser.
  These repeat, one run after another, until 30 seconds before the tabs stop.
- **Freshness.** `--freshness-probe` exports a three-span trace every two
  seconds and asks for it every 100 ms until all three spans are returned.
  That is the time from an accepted span to a readable one.

The harness starts the browser tabs and the SDK runs through
`--side-command`, together with the exporters, and waits for the command
before it measures the containers. The command gets the Studio origin, the
ingestion port, the services, the first user's credentials, and a path for
its JSON output in its environment: `JUNJO_BENCHMARK_STUDIO_URL`,
`JUNJO_BENCHMARK_INGESTION_PORT`, `JUNJO_BENCHMARK_SERVICES`,
`JUNJO_STUDIO_E2E_EXISTING_EMAIL`, `JUNJO_STUDIO_E2E_EXISTING_PASSWORD`, and
`JUNJO_BENCHMARK_SIDE_OUTPUT`. The result holds that output under
`side_activity`.

It needs what those parts need: the frontend's dependencies and Playwright's
Chromium (`npm ci` and `npm exec playwright install chromium` in
`frontend/`), and `uv` for the SDK's project.

Build the baseline and the candidate images first and select each with
`JUNJO_BENCHMARK_COMPOSE_OVERLAY`, as "Comparing production candidates"
describes. Then run each build, alternating, at least three times:

```bash
uv run python real_world.py --skip-build \
  --label baseline --output /tmp/junjo-real-world/baseline-1.json
uv run python real_world.py --skip-build \
  --label candidate --output /tmp/junjo-real-world/candidate-1.json
```

Each run prints its own numbers and writes the harness result, the services'
logs, and the harness's log beside each other. Print the runs side by side,
one column per build:

```bash
uv run python real_world_report.py \
  baseline=/tmp/junjo-real-world/baseline-1.json,/tmp/junjo-real-world/baseline-2.json \
  candidate=/tmp/junjo-real-world/candidate-1.json,/tmp/junjo-real-world/candidate-2.json
```

Repeat the comparison at a heavier rate, where ingestion and the backend
compete for the profile's one vCPU. `--export-interval-ms 25` offers four
times the spans.

Compare a run with its neighbours, not with a run from another hour. The
backend spends its whole CPU quota in these runs, so the page loads a run
completes follow how fast the host's CPUs were during it. Ingestion does the
same work in every run at one rate, so its CPU seconds show that speed: when
they rise, page loads fall for every build. A build that looks slower in
runs where ingestion's CPU seconds are also higher has not been shown to be
slower.

The harness checks still decide whether a run counts: every export succeeded,
every acknowledged span is in canonical storage, neither service was killed
for memory or restarted, both stopped in order, and the browser activity ran
to its end. Everything the pages and the SDK experienced is reported and not
gated: page outcomes and latency, API responses that were 5xx, the default
Traces view coming back empty or shorter than the full list, SDK runs shown,
freshness, exports refused and retried, export latency, and each service's
CPU and peak memory. Every trace the exporters send has LLM spans, so the
default view and the full list hold the same traces, and a shorter default
view is missing some. The script sets no thresholds. Compare the candidate with the baseline from the same
round, and bring a difference in either direction to the maintainer with the
numbers.

What these runs do not show:

- The exporters' traces are one root with flat children. Only the SDK's run
  has the nesting, events, and Store state of a real Workflow or Agent.
- Four tabs are one person moving quickly. They are not many people.
- A run lasts 90 seconds, so it sees the first cold flushes and the first
  indexer cycles. It does not show a deployment with weeks of cold files.

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

The pinned revision predates the Rust backend. Its Python backend serves the
two setup routes at other paths and needs settings this overlay no longer
provides. Pass `--first-user-path /users/create-first-user` and
`--api-keys-path /api_keys`, and set `JUNJO_BENCHMARK_COMPOSE_OVERLAY` to a
Compose file that gives the `backend` service `JUNJO_LOG_LEVEL: warning` and
the two session secrets named in that revision's `.env.example`.
