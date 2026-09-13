# Reproducing the comparison

Use fresh baseline and candidate checkouts at
`318201a856f72eb61a6a2fce86afc0b15b21432d`. Apply `final-notification.diff` and
`store-ownership.diff` from the parent directory to the candidate. The other
diffs preserve rejected or earlier experiment variants; do not combine them.

Build both ingestion images and the unchanged backend before measurements,
using each checkout's canonical Studio Dockerfiles and `apps/studio` as build
context. Use the `production` target. The archived drivers select these tags:

| Tag | Source |
| --- | --- |
| `junjo-durability-baseline:local` | Unchanged ingestion |
| `junjo-durability-backend:local` | Unchanged backend, used with every ingestion variant |
| `junjo-robustness-explicit-drop:local` | Ingestion with `final-notification.diff` |
| `junjo-robustness-ingestion:local` | Earlier `initial-lock-scope.diff` experiment |
| `junjo-robustness-try-send:local` | Earlier `try-send-notification.diff` experiment |

The baseline-rebuild controls used the unchanged production source with and
without the added test module. `baseline-binary-proof.json` records exact
binary/section equality. Record fresh hashes when rebuilding; base-image and
OS-package tags can change over time even with an unchanged application lock.

The reusable benchmark scripts live in the final working tree under
`apps/studio/ingestion/benchmarks`. Run them with the backend's locked Python
environment. Archived drivers contain the actual repository and temporary
paths used for these runs; change those roots when reproducing elsewhere.
`run_drop_coverage.py` runs two alternating pairs for the final correction's
mixed, serial, sparse and full-batch shapes. The `drop`/`old` cases in
`run_remaining_controls.py` define its sustained 6.4-million-span workload.
`images-affinity.yaml` belongs only to the separately labelled affinity
diagnostic; do not use it to replace ordinary-profile measurements.

For SDK confirmation, build `Dockerfile.sdk` with the frozen `requirements.txt`
in this directory. Point the archived confirmation driver at the baseline SDK
source and the candidate SDK source. It uses the reusable candidate
`sdks/python/benchmarks/store_ownership.py` for both variants. The initial SDK
driver additionally used `store-copy-patch-experiment.diff` and
`store-merged-experiment.diff`.

Run unchanged-versus-unchanged controls on the intended measurement host first.
Keep builds, validation suites and other workloads outside measurement rounds.
Every run must preserve offered work and pass delivery checks before comparing
performance. Do not count the failed or contaminated runs as passing evidence;
their disposition is recorded in the parent report.
