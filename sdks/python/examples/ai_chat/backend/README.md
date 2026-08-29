# Junjo AI Chat backend

This package is the backend half of Junjo's restored hybrid Workflow and Agent
example. The canonical architecture, run instructions, API contract,
telemetry configuration, and acceptance scenarios live in the
[example README](../README.md).

The package intentionally contains only application-owned domain,
orchestration, provider/persistence adapter, eval, and HTTP layers. Junjo owns
Agent and Workflow execution; the application owns prompts, providers,
persistence, transport, image artifacts, and product-quality evaluation.

The canonical full-stack development environment is the two-service
`compose.yaml` in the parent directory. This backend image is built from the
`sdks/python` workspace context so it installs the exact local Junjo source and
the AI Chat package from the same lockfile. Compose mounts its named data
volume at `/data`; native execution uses `runtime-data` beside this package.
The parent `.env` is the only Compose environment file and is required; do not
create a second backend environment file.
The SDK and backend source trees are bind-mounted, and watchfiles polling is
enabled, so Python edits reload the running FastAPI process without rebuilding
the image. Dependency changes still require a rebuild.
Both execution modes expose the backend on `http://localhost:26252` by default.

## Junjo Evaluation reference declaration

AI Chat owns one small application declaration at
`ai_chat.evals.harness:harness`. Junjo owns the Studio client, DTOs, targets,
evaluators, runner, resume behavior, telemetry context, and installed CLI.
The `pyproject.toml` setting selects that object explicitly, so there is no
import scan or application-local command implementation.

AI Chat uses its existing parent `.env` for both normal application settings
and commands run from this checkout. The app and CLI connect to the same Studio
deployment, but use separate credentials with separate authority:

```dotenv
# Developer environment or agent -> Studio backend REST API. Sign in to Studio,
# open Access Tokens, create a scoped developer access token, and copy it.
JUNJO_AI_STUDIO_BACKEND_BASE_URL=http://localhost:26154
JUNJO_AI_STUDIO_CLI_TOKEN=jcli_...

# AI Chat application -> Studio OTLP ingestion. Create an Application Telemetry
# API key from Studio's API Keys page.
JUNJO_AI_STUDIO_OTLP_ENDPOINT=localhost:26155
JUNJO_AI_STUDIO_OTLP_INSECURE=true
JUNJO_AI_STUDIO_API_KEY=jtel_...

# Browser links -> source-development Studio frontend.
JUNJO_AI_STUDIO_FRONTEND_BASE_URL=http://localhost:26151
```

These are host-facing values because evaluation execution records the real Git
revision from this checkout. The AI Chat Compose file translates the
application container's OTLP target to `host.docker.internal:26155` while
retaining this one environment file.

Run commands from `sdks/python/examples/ai_chat/backend`; the CLI reads the
configured harness from that package's `pyproject.toml`. Target discovery does
not construct a model provider or start telemetry:

```bash
uv run --env-file ../.env junjo eval targets list
uv run --env-file ../.env junjo eval capabilities
```

The three stable target keys are `node:turn.date_response:v1`,
`workflow:turn:v1`, and `agent:chat:v1`. Their Studio names are
`CreateDateIdeaResponseNode`, `Chat Turn Workflow`, and `AI Chat Agent`.
They share the strict JSON input `{"message": "..."}` and evaluator
`text.quality:v1`, whose expectation is `{"rubric": "..."}`.

Create `input.json` and `expectation.json` with those values, then author and
lock a dataset:

```bash
uv run --env-file ../.env junjo eval dataset create \
  --key local-place-realism-v1 \
  --name "Local place realism"

uv run --env-file ../.env junjo eval dataset add \
  --dataset-id DATASET_ID \
  --case-key brooklyn-date-1 \
  --evaluation-name "Response place realism" \
  --target-kind workflow \
  --target-key turn \
  --input-version 1 \
  --input input.json \
  --expectation expectation.json \
  --evaluator-key text.quality \
  --evaluator-version 1

uv run --env-file ../.env junjo eval dataset lock \
  --dataset-id DATASET_ID
```

Run the locked cases from a clean committed checkout. The same `.env` also
provides the real provider and OTLP exporter settings:

```bash
uv run --env-file ../.env junjo eval run execute \
  --dataset-id DATASET_ID \
  --request-key baseline-20260727 \
  --run-label baseline

uv run --env-file ../.env junjo eval run resume \
  --run-id RUN_ID
```

The runner is sequential, reuses one provider and telemetry runtime, creates
fresh per-case application dependencies, binds execution identity before
judgment, and never re-executes an Attempt whose subject is already bound.
Evaluation spans retain the truthful `junjo.examples/ai-chat` application
Resource; there is no fake eval service.

The harness also declares the application-owned
`local_place.quality:v1` composite evaluator. One structured provider response
judges the qualitative rubric and transcribes literal recommended-place
claims; deterministic application code resolves every claim against the
example's source-attributed current-place snapshot. The snapshot is bounded
evaluation data, not application retrieval logic: ordinary AI Chat requests do
not read it, and Studio or the Junjo SDK do not own its place semantics.

Generated cases run the same real Node, Workflow, or Agent before Studio adds
their explicit provenance. The observed output remains evidence, never an
automatically accepted expectation:

```bash
uv run --env-file ../.env junjo eval case generate \
  --dataset-id DATASET_ID \
  --case-key generated-agent-1 \
  --evaluation-name "Response place realism" \
  --target-kind agent \
  --target-key chat \
  --input-version 1 \
  --input input.json \
  --expectation expectation.json \
  --evaluator-key text.quality \
  --evaluator-version 1
```

Query and compare without provider credentials:

```bash
uv run --env-file ../.env junjo eval run list --dataset-id DATASET_ID
uv run --env-file ../.env junjo eval run get --run-id RUN_ID
uv run --env-file ../.env junjo eval run compare \
  --baseline-run-id BASELINE_RUN_ID \
  --candidate-run-id CANDIDATE_RUN_ID
uv run --env-file ../.env junjo eval attempt evidence manifest \
  --attempt-id ATTEMPT_ID
uv run --env-file ../.env junjo eval attempt evidence spans \
  --attempt-id ATTEMPT_ID \
  --span-id SPAN_ID
uv run --env-file ../.env junjo eval attempt evidence full \
  --attempt-id ATTEMPT_ID
```

Inspect Run and Attempt summaries first, then manifests for results that need
attention, then the exact spans named by those manifests. Full evidence is for
questions that genuinely require the complete trace.

AI Chat's `text.quality` evaluator is a qualitative binary judge. Its rubric
must be calibrated with known-good, known-bad, and boundary examples. It can
judge whether a response is useful, specific, and plausible from the supplied
text, but it is not proof that a named venue currently exists, is open, or is
located in the requested neighborhood. Verify those current facts separately
against a trustworthy current source.

Every command writes one versioned JSON envelope to standard output.
Diagnostics use standard error. Exit status `5` means an Attempt error, `6`
means a completed failing evaluation, `7` means evidence is not ready, and `8`
means Studio remained unavailable.

The programmatic surface is the same public SDK:

```python
from junjo.evaluation import EvaluationExecutor
from junjo.studio import StudioClient

from ai_chat.evals import harness

async with StudioClient(base_url=studio_url, token=studio_token) as studio:
    async with EvaluationExecutor(client=studio, harness=harness) as evaluation:
        run = await evaluation.run(
            dataset_id=dataset_id,
            request_key="baseline-20260727",
            run_label="baseline",
        )
```

Studio never executes this checkout. Complete trace payloads still enter
through authenticated OTLP; the REST control plane stores only bounded
dataset/result records and canonical evidence references.
