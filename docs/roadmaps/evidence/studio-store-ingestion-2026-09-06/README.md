# Store ownership and ingestion robustness — September 2026

Base: `318201a856f72eb61a6a2fce86afc0b15b21432d`. SDK 0.67.0; Studio 0.83.0.

The Store ownership correction is validated. The notification correction fixes
the reproduced deadlock. **On September 7, the maintainer explicitly accepted
the current changes and the possible measured performance cost under the
benchmark uncertainty.** That product decision supersedes this investigation's
original recommendation to hold the ingestion change. It does not turn the
historical failed numeric gates into passes or establish zero regression.
The follow-up [performance mechanics investigation](../studio-performance-mechanics-2026-09-07/README.md)
records the profiling evidence and optimization priorities.

No production batching, flush interval, storage synchronization,
allocator, compression, memory limit or authentication setting was changed.

## Changes and correctness

- **Notification deadlock:** release the WAL write guard immediately before the
  existing notification send. The production-sized queue reproduction fills
  all 16 entries, polls the next export, and checks that the WAL remains
  acquirable while that export waits. The unchanged implementation fails this
  assertion. The correction lets the real flusher proceed and preserves all
  17,001 spans, including the partial tail, through orderly shutdown/reopen.
  No queue enlargement, polling loop or new synchronization primitive.
- **Store ownership:** merge retained runtime fields and the incoming patch,
  then deep-copy that candidate once before validation. This isolates caller
  values and retained state without copying replaced old fields needlessly.
  The existing named-action API, detached reads, validation and transition
  evidence remain. Five new regressions fail on the unchanged implementation
  and pass with the correction, including nested Pydantic models and a
  mutating validator that rejects its input.
- **Termination policy:** the user explicitly accepted loss of acknowledged
  pending telemetry on abrupt termination. ADR-001 records that decision.
  Healthy ingestion and completed orderly shutdown still preserve accepted
  spans. No per-request flush, receipt or fsync was added. This is not a new
  host-power-loss or storage-failure guarantee.
- **Deployment reset:** both distribution READMEs now link to the canonical
  reset procedure. Docker volume deletion does not clear the application bind
  mount and can instead remove Caddy certificates. The procedure retains the
  old release/data, selects a fresh directory, checks both effective mounts,
  and explains initialization and rollback.

## SDK performance

Production dependencies and the same Python 3.13 interpreter ran in fresh
0.5-CPU, 350-MiB containers with no swap. This is a controlled comparison
profile, not a new SDK minimum. An initial three-variant, seven-case matrix
covered scalar updates, large retained state, nested replacement, no-op,
prospective validation and complete eight-node workflows. The selected approach
avoids the redundant copy in the other ownership candidate.

Five alternating confirmation pairs then used the actual final SDK source,
with equal warmup/work counts and no overlapping build or validation suite.

| Workload | Baseline → candidate throughput | CPU per operation | p95 latency | Peak RSS |
| --- | --- | --- | --- | --- |
| Scalar, 30,000 updates/run | 7,773 → 8,058/s (+3.67%) | 63.70 → 62.32 µs (−2.17%) | 0.075 → 0.074 ms | 53.25 → 53.05 MiB |
| Eight-node workflow, 600/run | 97.33 → 96.61/s (−0.75%) | 5,129 → 5,187 µs (+1.13%) | 55.26 → 55.35 ms | 39.50 → 39.41 MiB |

The initial large nested replacement case measured +1.84% CPU; other large-state
cases were approximately flat or slightly improved. These are measured small
changes, not a claim of universal zero cost. Full workflows use normal SDK
telemetry configuration without a network exporter; the separate Studio
benchmark covers network ingestion. The ingestion-specific percentage gates
were not invented as SDK acceptance thresholds.

See [confirmation medians and ranges](comparison-sdk-confirmation.json),
individual `results/sdk-*.json` files, and the SDK reproduction drivers.

## Ingestion measurement and disposition

Every compared workload uses the same production backend and pinned baseline
or candidate ingestion image. Each service keeps its existing 0.5-CPU quota;
ingestion has 350 MiB and backend 450 MiB, with no swap. Source/image hashes are
in [provenance](provenance.json). The saved baseline was independently rebuilt:
the exact current-source build produces the same binary SHA-256. A rebuild
with only the additional test module also has identical runtime `.text` and
`.rodata` sections.

Each logical export receives unique span identities; retries reuse them.
Throughput counts fully acknowledged spans. After both services exit, the
harness reads canonical WAL streams and Parquet, verifies every acknowledged
identity, and reports missing, duplicate and unacknowledged rows separately.
Snapshots never count as another canonical copy. Partial-success responses and
failed exports fail acceptance. Canonical files are never read from a live
backend deployment.

The workload matrix includes paced concurrent ingestion plus authenticated
queries, unpaced saturation and cold rollover, serial exporters, sparse spans,
and full batches. Later runs add a ten-second idle observation period without
changing production timers. Reports include export p95/p99, query p95/counts,
cgroup CPU per acknowledged span, sampled container working set, cgroup peak,
post-work samples, OOM/restart state and orderly-shutdown delivery.

Results are deliberately separated by implementation and method:

| Result prefix | Meaning | Disposition |
| --- | --- | --- |
| `ingestion-baseline-*`, `ingestion-candidate-*` | Initial scoped-unlock candidate; three alternating pairs per shape | Saturation median throughput −8.87%, CPU +9.87%; fails the existing 5% throughput gate. |
| `ingestion-final-*` | Earlier try-send experiment; the historical filename does **not** designate the final implementation | Not accepted. Entire first round overlapped full Studio validation and is diagnostic only. Later clean runs still varied/slowed; the final full-batch pair was not completed after rejection. |
| `control-*` | Saved baseline, runtime-equivalent rebuilt baseline, and final explicit-drop correction | Unchanged-binary variation prevents reliable attribution. One baseline run had 50 final INTERNAL responses and fails acceptance. |
| `affinity-*` | Separate diagnostic: both services pinned to virtual CPU 0, with the same quotas/memory/work | Does not replace the supported-profile results. Variation remains; one baseline run had 17 final INTERNAL responses and fails acceptance. |
| `ingestion-drop-*` | Final explicit-drop correction, original CPU-affinity setting | Workload coverage; interpret together with unchanged controls, not as standalone no-regression proof. |

The final correction's two original-profile saturation runs measured
**164,756 spans/s versus 186,532 for the two saved-baseline controls (−11.67%)**,
with ingestion CPU per span +11.45% and export p95 +11.35%. The
[comparison gate correctly fails](comparison-drop-sustained.json). Baseline
throughput ranged from 168,834 to 204,230 in those controls; separate affinity
controls varied further despite identical baseline binaries. This prevents
isolating the code's effect, and it does **not** turn the failing comparison
into a pass. No ingestion performance improvement is claimed.

Two baseline/candidate pairs for each remaining shape completed all offered
exports and all issued queries, without missing acknowledged spans, OOMs or
restarts. Their medians are shown here for completeness; favorable rows do not
override failed gates or unstable controls.

| Final-correction workload | Throughput change | Ingestion CPU/span change | Query p95 change |
| --- | --- | --- | --- |
| Paced mixed queries | −0.01% (offered-rate limited) | +7.64% | +21.08% — fails 10% gate |
| Serial exports | +12.20% | −10.78% | No queries |
| Sparse spans | +40.03% | −21.93% | No queries |
| Full batches | +11.46% | −5.78% | No queries |

See `comparison-drop-*.json` for medians, ranges, memory and export tails, and
the raw run files for actual query counts. Query workers use the existing
closed-loop workload, so completed query counts vary with latency. The mixed
query p95 median was 72.04 → 87.23 ms; that comparison also fails its gate.

Two saturation runs returned WAL-write INTERNAL responses (50 and 17 exports).
All fully acknowledged spans in those runs survived, but that does not make
failed offered work acceptable benchmark evidence. Their exact storage error
was not captured: the inherited benchmark used Python's `warning` spelling
for the Rust log filter. The benchmark now uses Rust's `warn` and saves service
logs before cleanup. The cause remains unestablished; no speculative runtime
error mapping or storage change was introduced.

Docker working-set samples are not precise process RSS; cgroup peaks include
page cache. The load generator runs outside the constrained containers.
Distinct-ID generation adds client work, so absolute throughput must not be
compared with the old reused-identity generator. This shared Apple/OrbStack
host had unrelated CPU-heavy activity; CPU affinity did not provide an isolated
physical CPU. A connection attempt to the configured Linux workstation did not
respond and made no remote changes.

**Follow-up measurement (originally a release gate):** the maintainer accepted
the current change on September 7. Repeat the final baseline/candidate matrix on an available,
quiet supported resource profile after unchanged-versus-unchanged controls are
stable. Retain the existing 5% throughput and 10% mixed-query-p95 limits from the
owning ingestion performance evidence, and review CPU, memory and tails too.
Do not widen limits, increase resources, reduce offered work, discard failed
runs or cherry-pick a favorable ordering to approve this change.

## Validation and reproduction

Validation logs are retained under `validation/`. The full SDK checks passed:
Ruff, 438 pytest tests, ty, Griffe (560 public objects), package build and Twine.
Studio passed backend, Rust, frontend, contracts, lint/build and proto checks;
the final explicit-drop run passed 935 backend tests (2 skipped), 39 Rust tests
and 250 frontend tests, with 31 frontend contract tests run again separately.
The host's protoc 35.1 emitted the existing warning for expected version 30.2;
regenerated tracked protos remained unchanged. Production benchmark Dockerfiles
use their pinned protobuf compiler. Website installation,
Astro checks/build, documentation assembly/parity and 144 root tests passed.
Distribution validation covered 34 export/archive tests, 12 setup tests,
production-profile Compose rendering, both effective data mounts, and generated
archive/mirror equivalence in a disposable local clone. Two already-stale root
documentation metadata expectations were synchronized with the reviewed source;
no public-surface or content checks were removed.

The reusable entrypoints are component-owned benchmark scripts. The
`reproduce/` drivers preserve exact commands and local paths used in this
investigation; adjust repository/evidence roots and recreate the pinned images
when reproducing elsewhere. Production builds were completed before measurement
rounds. Build/test overlap in the earlier round is retained and excluded as
noted above, not silently deleted.

Two harness issues were corrected before the initial accepted-delivery matrix:
canonical WAL files use Arrow's stream reader, and normal backend SIGTERM exit
143 must be distinguished from ingestion's required successful shutdown exit 0.
The failed harness attempts are retained under `validation/`.

Repository guidance now treats low-resource performance as a product contract
and requires baseline evidence before ingestion/storage changes. The comparison
CLI refuses failed/unverified delivery and mismatched workloads, limits or CPU
affinity. Fast benchmark-accounting regressions are wired into existing CI.
Full performance comparisons remain a measured release/review gate; this change
does not claim to install an automated hardware performance runner.

The user's original Studio containers and data were not stopped, reset or
upgraded. No release, tag, dependency/version change or production deployment
was performed.
