# Composable application Stores: implementation evidence

Implemented against `1faadb580d6a7be7f2824bcbfa3394a4c3884a08`, under
[ADR 0016](../../../adr/0016-composable-application-stores.md). The
[implementation map](../../COMPOSABLE_AGENT_APPLICATION_STORES.md) records the
scope and affected consumers. No release, deployment, database migration, or
changes to the user's running Studio stack were performed.

## Delivered behavior

- Agents accept an optional `store_factory` and an explicit `execute(store=...)`.
  Tools receive the selected typed application Store through `context.store`.
  Results and failure evidence distinguish detached application state from
  private Agent runtime state.
- Workflows can borrow that same Store. Execution identity, Graphs, observer
  snapshots, and private Agent bookkeeping remain independent. Subflows keep
  their isolated Stores and existing pre/post mapping actions.
- Concurrent borrowers use the existing Store commit lock. No lock spans a
  model request or execution. Read/replace actions retain existing semantics.
- Telemetry contract **3** records each execution's Store interval and
  checkpoints. Events remain attached once to the actual writer span. The SDK
  releases replay history when no active execution needs it.
- Studio separates physical Store transitions from execution/role boundaries.
  Agent application and runtime timelines, Workflow selection, manifests,
  selected-span evidence, Python DTOs, evaluation invocations, external Tool
  adapters, and the live E2E validator consume the new shape.
- Rust production ingestion, WAL/Parquet layout, protobufs, SQLite, and physical
  trace queries are unchanged. A preservation test covers the new attributes
  and events through OTLP conversion, WAL, and Parquet.
- The `junjo_openai_sdk` example uses a real OpenAI Responses client,
  OpenInference, a direct Node Tool, and a conditional Workflow Tool. Its README
  explains granular state and both ownership choices. The public index, SDK
  guides, root/SDK READMEs, and copyable setup instructions link to these owners.

Contract 3 requires coordinated SDK/Studio publication. Deployment pins and
package versions are left to the existing release workflow. Cross-trace writes
missing from a selected trace still produce incomplete replay; no cross-trace
Store index or compatibility parser was added.

## Validation

- SDK: Ruff, `ty --error-on-warning src`, **471 tests**, Griffe validation
  (**1,504 public objects, 231 API pages**), package build, and Twine validation.
- Native OpenAI example: **2 deterministic integration tests**, Ruff and ty.
  Both Store choices and both conditional branches use the real OpenAI client
  and OpenInference instrumentor with a mock HTTP transport. Three provider
  spans and Tool continuation are verified. No paid provider smoke test ran.
- Existing examples: **89 AI Chat tests and 6 external OpenAI Agents tests**
  pass with their owning pytest configurations and the updated workspace lock.
- Studio full suite: **964 backend tests**, 2 existing skips; **40 Rust tests**;
  **252 frontend tests**; frontend lint/build, REST/OpenAPI contracts, and proto
  regeneration. Final targeted tests also cover the shared projection and
  outside-Workflow writer navigation.
- Root tooling: **148 tests**, including current trace-evidence projections and
  the shared Store interval consumer.
- Shared contracts: **9 schemas, 6 Workflow fixtures, 34 Agent producer fixtures,
  4 Agent consumer fixtures, 41 invalid fixtures, 22 fingerprint vectors,
  7 replay vectors, and 8 external OpenAI Agents integration vectors**. The
  validator rejects 601 malformed scalar mutations. Regenerating all contract
  artifacts leaves every file byte-for-byte unchanged.
- Website: `npm ci`, Astro checks/build, complete route/link/API validation,
  documentation assembly/parity (**270 files**), and the required high-severity
  production audit. The existing moderate `devalue` advisory is outside this
  feature; the high-severity audit passes.
- The host's existing protobuf compiler version warning remains; regenerated
  tracked protobufs are unchanged.

The new example is included in `python-examples-smoke.yml`, with independent
lint, typing, and deterministic native SDK/OpenInference tests. Its exact
README/CI commands and `main.py --help` pass; Actionlint validates the workflow.

## Live transport and evidence proof

A disposable canonical Studio stack used the unchanged production ingestion
image and current backend source on the supported benchmark allocation:
**0.5 CPU / 350 MiB ingestion, 0.5 CPU / 450 MiB backend, no swap**. It had its
own temporary data mount, user, and API keys, created through public APIs.

The [shared-Store workload](studio-shared.json) offered and acknowledged
**24,000 unique spans in 4,000 exports** while **282 authenticated trace-evidence
queries** reconstructed the Agent and nested Workflow. Every query returned
200 with no integrity diagnostics. After both services exited, canonical
storage contained all 24,000 spans: 18,498 in Parquet and 5,502 in WAL, with no
missing, duplicate, or unacknowledged rows, OOMs, or restarts. The six-span
warmup trace is separate from offered-work and delivery counts.

[The HTTP trace response](shared-store-live-trace.json) retains the physical
Store once and verifies Agent application interval `(2,5]`, Workflow interval
`(3,4]`, and independent private runtime state. It demonstrates nonzero
starting revisions and shared writer evidence through the real transport.

## Performance comparison and limits

[Raw comparisons](comparison.json), [resource/image provenance](profile.json),
and [exact commands](commands.json) retain all rounds. Builds and test suites
finished before measurements; baseline and candidate processes ran sequentially
in alternating order. No resources, offered work, or acceptance limits changed.

The unchanged SDK baseline was captured before implementation. Three initial
scalar runs used an empty retained list, and three initial Workflow runs used
128 entries. The final alternating comparison used **128 retained entries for
both workloads and both variants**; it is compared only with its matching
baseline, not with the earlier empty-list scalar runs. Each fresh SDK container
used the same pinned Python/dependency image, 0.5 CPU, 350 MiB, and no swap.

| Final SDK workload | Baseline → candidate throughput | CPU/operation | p95 | Peak RSS |
| --- | --- | --- | --- | --- |
| 30,000 scalar commits, 1,000 warmup | 1,587.8 → 1,580.4/s (−0.46%) | 315.1 → 316.3 µs (+0.38%) | 0.368 → 0.373 ms | 53.40 → 40.04 MiB |
| 600 complete eight-Node Workflows, 30 warmup | 98.91 → 100.05/s (+1.16%) | 5,048 → 4,994 µs (−1.07%) | 55.49 → 55.59 ms | 39.76 → 39.38 MiB |

The scalar memory change reflects releasing history outside active execution
boundaries. These are measured workloads, not a general concurrency or network
throughput claim. SDK runs use normal telemetry without a network exporter.

Three Studio baseline/candidate pairs used equivalent six-span Agent/Workflow
fixtures, with baseline contract 2 and candidate contract 3, **24,000 offered
spans per run**, two concurrent evidence-query workers, and identical resource
limits and ingestion image. All six runs delivered every span and completed
every issued query. Paced throughput was approximately 2,401 spans/s in both.
The actual query counts were 274/282/272 baseline and 264/270/286 candidate.

| Studio measurement | Baseline median | Candidate median |
| --- | --- | --- |
| Evidence-query p95 | 29.61 ms | 34.09 ms (+15.13%) |
| Backend cgroup CPU per completed query, including concurrent ingestion work | 10.97 ms | 11.07 ms (+0.96%) |
| Backend peak cgroup memory | 256.15 MiB | 166.57 MiB |

**The query-p95 comparison does not establish latency neutrality.** Its median
exceeds the historical 10% mixed-query guidance. Unchanged baseline p95 ranged
28.85–34.72 ms and candidate p95 28.71–36.00 ms; the ranges overlap and CPU per
query is roughly flat. This shared-host result is inconclusive for attributing
the tail change, and it is not a passed or waived performance gate. Stable-host
confirmation is needed before claiming unchanged query latency. Cgroup memory
includes cache, varies materially across rounds, and is not a process-RSS
improvement claim. No speculative production optimization was added to chase
these noisy tails.

## Reproduction and command corrections

- Archive baseline SDK `src`/`benchmarks`, backend `app`, and the baseline
  `tool_invokes_nested_workflow` fixture at the base commit into
  `/tmp/junjo-composable-stores-1faadb5`.
- Build the two backend images with [backend.Dockerfile](reproduce/backend.Dockerfile)
  and the corresponding backend directory as context. The base image's backend
  lock hash must match `profile.json`. The actual image IDs are recorded in every
  Studio run; overlays replace development source mounts with only disposable
  data mounts.
- [compare.py](reproduce/compare.py) runs the alternating measurements, using
  [studio_evidence.py](reproduce/studio_evidence.py) to specialize the existing
  delivery/resource harness. It preserves canonical post-shutdown delivery
  verification and queries the changed evidence endpoint during ingestion.
- For the shared proof, use the candidate overlay and set
  `JUNJO_STORE_BENCHMARK_FIXTURE` to the current `shared_application_store.json`.
  Use the same Studio arguments recorded in `commands.json`.

Initial implementation checks exposed and corrected old terminal-capture fault
hooks, a missing `Node.execute` parent identity in the new example, and outdated
single-owner E2E projection code. An initial cross-example pytest invocation
inherited the SDK's strict asyncio configuration; example tests must run with
their owning project configuration. Workspace `uv sync --package` may remove
other members' development dependencies; use `--no-sync` for concurrent checks
in an already prepared workspace or restore `uv sync --all-packages --extra dev`.
No production behavior or test expectations were relaxed to hide these issues.
