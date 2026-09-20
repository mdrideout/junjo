# Full library and examples revalidation

Validated commit `f83dd99382a23df0717c1844310043737712a6f0` on
`codex/junjo-for-coding-agents`, on 2026-09-20. Production source was not changed
during this review. The SDK, Studio, and example environments were installed
fresh in the branch worktree. Studio was rebuilt against that worktree while
preserving its existing local data.

The non-demonstration findings below were subsequently addressed; see
[fixes and validation](FIXES.md). The original results are retained as evidence.

## Findings

### P2 — The native OpenAI example prints the API origin as its Studio link

`sdks/python/examples/junjo_openai_sdk/.env.example:7` supplies
`JUNJO_STUDIO_URL=http://localhost:26154`. `main.py:39` prints this value as
**Studio**, and the README tells readers to open it. This address returned
`{"app":"Junjo AI Studio","version":"0.84.1","health":"/health"}` during
validation, rather than the frontend. The development frontend is on port
26151. Correct the example's browser-facing default; its OTLP endpoint is
already correct.

### P2 — AI Chat can persist conflicting names in one generated contact

The live Grok contact-coherence evaluation failed: structured state contained
**Olivia Bennett**, while the biography began **Hi, I'm Elena**. The avatar
judgment passed. This disagreement was retrieved from Studio's backend-verified
Workflow ending state, independently of the model judge's explanation.

`contact_workflow/graph.py:42-44` runs biography creation before name creation.
`contact_workflow/nodes.py:97-105` passes personality, location, age, and sex to
the name generator, but not the already generated biography. Conversely, the
biography generator has no canonical name. These application prompts can
therefore independently invent identity facts. Define the name once and supply
it to biography generation, or otherwise make the second generation consume
the identity established by the first. No SDK Store or telemetry change is
needed for this finding.

The failing run is `W5nTyi0yLwT13vN98tA3W`. Open its
[Workflow in local Studio](http://localhost:26151/workflows/ai-chat/1426828b9dbc571fe4deb5b6cd0f15ba/7f8d13e705c0777d).
See [grok-contact-failure.json](grok-contact-failure.json) for the resolved
execution, fictional profile evidence, and actual Store writers.

### Compatibility caveat — Older Python 3.11 patch releases

The full SDK suite on the machine's Python **3.11.6** reported **465 passed,
6 failed**. Explicitly parameterized `Agent[...]()` and `Tool[...]()`
construction raises `TypeError: super(type, obj): obj must be an instance or
subtype of type` when Python's typing machinery assigns `__orig_class__` to
the frozen, slotted dataclass. Unparameterized construction succeeds.

The same affected tests and then the entire **471-test suite passed on
3.11.15**. Python 3.12.9, 3.13.13, and 3.14.3 also pass all 471 tests. Do not
interpret the original failure as loss of support for the current 3.11 line.
The frozen/slotted Agent and Tool declarations also exist on `master`; this
is an existing compatibility constraint now exercised by the explicit generic
constructors in the new Store tests and example. The package currently declares
`requires-python >=3.11` without a patch-level qualification. The exact first
working 3.11 patch release was not established.

## Intentional demonstration results — preserved

### Base joke evaluator rejects three generated jokes

The real Gemini base Workflow completed successfully, including concurrent
Nodes, the conditional path, isolated Subflow, and mapped results. Its separate
six-case joke-quality evaluation reported **3 passed, 3 failed**. All three
failures were negative quality judgments against the existing minimum humor
score of 7/10; one also cited incorrect use of “kits” for puppies. They were
not transport failures, missing credentials, Store corruption, or SDK crashes.
The rubric is in `create_joke_node/test/test_prompt.py:13-19`. These rejections
are an intentional part of the example, confirmed by the user, and are not a
defect to fix. The joke prompts, evaluator rubric, thresholds, and execution
behavior remain unchanged. A successful Workflow execution does not establish
that its generated joke meets the application's rubric.

## Automated validation

| Area | Result |
| --- | --- |
| SDK Python 3.11.15 | 471 passed |
| SDK Python 3.12.9 | 471 passed |
| SDK Python 3.13.13 | 471 passed |
| SDK Python 3.14.3 | 471 passed |
| SDK Ruff, ty, Griffe | Passed; 1,504 public objects, 231 API pages |
| SDK wheel/sdist and Twine | Passed |
| Minimum OpenAI Agents dependency, 0.21.1 | 39 integration tests passed |
| Native OpenAI SDK example | 4 integration tests and ty passed |
| OpenAI Agents example | 6 deterministic tests passed |
| AI Chat backend | 89 infrastructure tests and ty passed |
| AI Chat frontend | 29 tests, lint, production build passed |
| AI Chat Compose | Gemini and Grok clean-volume startup, HTTP, rebuild, and storage-preservation checks passed |
| Studio complete runner | Passed in one complete invocation |
| Studio backend | 964 passed, 2 existing skips |
| Studio ingestion | 40 Rust tests passed |
| Studio frontend | 257 tests in 66 files passed, including installed Mermaid and Graph/tree/state/URL interactions |
| Studio lint, build, REST contracts, proto | Passed; generated artifacts unchanged |
| Shared telemetry contracts | Regeneration and validation passed; contract tree unchanged |
| Root tooling | 148 tests and 72 subtests passed |
| Website | Install, assembly, checks, build and parity passed; 258 pages, 252 routes, 270 assembled documents |
| Website production dependency audit | High-severity gate passed; existing moderate `devalue` advisory remains |

Contract validation includes 34 Agent producer fixtures, four consumer fixtures,
41 invalid fixtures, six Workflow fixtures, eight OpenAI Agents integration
vectors, and rejection of 601 malformed scalar mutations.

## Live example and integration coverage

| Example/path | Result |
| --- | --- |
| Getting started entrypoint | Completed with expected final count and items |
| Base entrypoint | Completed using real Gemini; graph asset rendering also passed |
| Base live evaluations | 3 passed, 3 quality failures described above |
| AI Chat, Gemini | All 13 live evaluations passed, including contact/avatar, directives, persona/history, image editing, and Agent tool policy |
| AI Chat, Grok | 12 passed, 1 contact identity failure described above; image editing and Agent tool policy passed |
| OpenAI Agents command entrypoint | Completed and ingested mixed-runtime trace |
| OpenAI Agents HTTP entrypoint | Real HTTP request returned the expected response; 27 spans under one `POST /recommendations` root, all parents present, health probes excluded |
| Standalone evaluation application | Fresh wheel installation outside the workspace; Node/Workflow/Agent baseline, intentional candidate regression, compare/resume, evidence and revoked-token checks passed |
| Native Agent Studio validator | Real SDK composition, OTLP, storage, semantic projection and Store replay passed |
| Native OpenAI SDK example | Four fresh CLI cases: both orders × owned/borrowed Stores; all passed with exact full/manifest/selected CLI-to-API equality |
| Workflow → Agent → Workflow | One application Store with independently verified intervals `(0,4]`, `(0,3]`, and `(1,3]` |

The native OpenAI example used its real application, OpenAI client, driver,
OpenInference instrumentor, exporter, ingestion, backend, and UI. Only OpenAI
HTTP responses were deterministic fixtures. No OpenAI key/model was configured
for a paid provider run. Gemini and Grok evaluations used the existing local
provider credentials and real provider calls.

The native OpenAI cases each retain 16 spans including evaluation spans, three
OpenInference model spans under their respective Junjo model requests, a direct
lookup Node below its Tool, and a conditional Workflow below its Tool. Store
mutations occur once on their actual writer Nodes. The application Store and
private Agent runtime Store remain distinct; normalized usage and final
eligibility agree across state, Tool output, CLI, and Studio.

The base example's parent Workflow and isolated Subflow have different Store
IDs, and both reconstruct successfully. The OpenAI Agents example's stateless
native Agent correctly reports application state as not applicable while its
private runtime Store and nested Workflow Store verify. These absent application
Stores must not be mistaken for reconstruction failures.

## Browser verification

Checked newly ingested executions through the running branch frontend:

- The four-case evaluation Run displays 100%, four passes, zero failures, and
  zero errors, matching the CLI. **View spans** resolves the precise Agent.
- Agent application and runtime histories render explicit nulls. A policy
  transition's writer link selects its actual `EvaluateReturnPolicyNode` in
  Raw trace; **Agent diagnostics** returns to the correct Agent.
- The Tool inspector describes shared/separate Stores correctly and opens the
  nested Workflow. The ineligible graph dims the unexecuted eligible Node and
  selects the correct executed Node when clicked.
- The caller Workflow's application list includes its four transitions. Direct
  selection of the nested policy writer remains **2 / 4**; Next reaches
  **3 / 4** and the caller's **4 / 4**, rather than switching intervals.
- Node deep links reload the selected span. Browser Back/Forward return to the
  Agent and selected Workflow Node. Raw trace visibly preserves Tool/Node,
  Tool/Workflow, and model-request/provider parentage.

No new failure was found in these navigation paths. This is not a claim that
every unrelated screen, viewport, or production deployment was exercised.

## Evidence and execution notes

- [Native OpenAI CLI/API parity](parity-report.json)
- [Shared composition intervals](composition-report.json)
- [Base, mixed-runtime, and AI Chat Store evidence](live-examples-evidence.json)
- [HTTP mixed-runtime span tree](openai-agents-http-evidence.json)
- [Installed-package evaluation run identities](evaluation-live.json)
- [Native Agent validator identities](agent-live.json)

Detailed logs and scratch harnesses are retained locally under
`/tmp/junjo-full-revalidation-20260920`. Temporary validator users, telemetry
keys, and developer tokens were removed through public APIs. The temporary
OpenAI Agents HTTP server was stopped. The existing local Studio data and
unrelated application stacks were preserved. No host access to live SQLite
files occurred.

The first local Python compatibility command set `--python` only; its nested
`uv run` typing test then rebuilt that temporary environment using the repo's
3.13 pin. Those environment-related failures were discarded and the matrix was
rerun with inherited `UV_PYTHON`, as CI does. Directly invoking `ty` from inside
the non-installable OpenAI example also missed the workspace environment;
the documented `uv run --package ... --group dev ty ...` command passed.
Scratch evidence assertions initially assumed executable names and ownership
were fields on Store views; correcting them to use span names and executable
annotations allowed verification of the same already-ingested evidence. No
product code was changed to accommodate these validation-script mistakes.
