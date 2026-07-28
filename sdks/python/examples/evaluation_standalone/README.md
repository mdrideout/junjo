# Standalone Junjo Evaluation declaration

This directory is intentionally excluded from Junjo's uv workspace. It models
an independent application that depends only on the installed `junjo`
distribution and declares Node, Workflow, and Agent evaluation targets.

Create a virtual environment and install a built Junjo wheel plus this
application:

```bash
python -m venv .venv
.venv/bin/pip install /path/to/junjo-WHEEL.whl .
```

The declaration is provider-free and safe to inspect:

```bash
.venv/bin/junjo eval targets list
```

With `JUNJO_STUDIO_URL` and a separately scoped
`JUNJO_AI_STUDIO_CLI_TOKEN`, use the same CLI to create a dataset. Each target
accepts:

```json
{"value": 2}
```

Use evaluator `junjo.exact:v1` with:

```json
{"expected": 4}
```

The example's Agent uses Junjo's deterministic scripted driver so the package
boundary can be validated without a model-provider dependency. A real
application replaces only that application-owned factory and resource context;
Studio client, dataset, runner, result, resume, and CLI mechanics remain in
Junjo.
