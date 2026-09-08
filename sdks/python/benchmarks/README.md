# Store ownership performance

`store_ownership.py` measures scalar patches, nested model replacement, no-op
updates, prospective validation and complete eight-node workflows. It reports
completed work, latency, process CPU per operation, peak RSS and Linux RSS
before work, after work and after releasing the workload objects.

Use the same locked dependencies and interpreter for baseline and candidate.
Select each source tree with `PYTHONPATH`; run each case in a fresh process.
Pass the same `--case`, `--iterations` and `--size` (nested list length) to both,
with distinct `--label` and `--output` paths. Alternate order across repeated
runs and retain raw JSON with source hashes and actual container limits.

The September 2026 comparison uses the existing ingestion benchmark's
0.5-CPU/350-MiB/no-swap container allocation for each SDK process. This is a
controlled comparison profile, not a new minimum SDK resource requirement.
Full workflows use Junjo's normal default telemetry configuration, without a
network exporter; network ingestion is measured by Studio's separate harness.

Compare CPU, latency and memory together. Do not accept a fix from an isolated
microbenchmark alone, raise resources to hide a regression, or copy arbitrary
ingestion acceptance percentages into an SDK performance policy.

The [September 2026 comparison](../../../docs/roadmaps/evidence/studio-store-ingestion-2026-09-06/README.md)
records the baseline, candidate hashes, repeated workflow results and limits of
the evidence.
