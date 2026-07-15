# Python documentation ownership

This directory is the canonical source for Python SDK documentation. The public
site is rendered by Starlight, while Python narrative content, API extraction,
examples, and the explicit public surface remain owned and validated here.

- `content/` is canonical Markdown owned by the Python SDK.
- `api-public-surface.json` is the reviewed publication contract for modules,
  symbols, members, routes, and anchors.
- `export_api.py` resolves that contract with Griffe's automatic reST,
  Google-, and NumPy-style docstring parsing and emits Starlight Markdown.
- Generated API pages are staged outside this component and are never committed
  here.
- The retired RST source remains recoverable from repository history and the
  immutable legacy-release snapshot; it is not an active current-source input.

## Local validation

From `sdks/python`:

```bash
uv sync --frozen --extra dev
uv run python docs/export_api.py validate
```

From the repository root, assemble and validate the public site:

```bash
uv sync --project tooling/docs --frozen
python3 tooling/docs/assemble_public_docs.py --write
npm --prefix apps/website run validate
```

When an intentional public API change adds or removes a documented symbol,
update `api-public-surface.json` in the same review. Validation fails if Griffe
cannot resolve and render any contracted object.

Assembly defaults to the `next` documentation channel and labels generated API
pages as source previews. Build `stable` only from the exact released checkout:

```bash
JUNJO_DOCS_CHANNEL=stable python3 tooling/docs/assemble_public_docs.py --write
```

The version in `pyproject.toml`, full source revision, and channel are embedded
in the API and assembly manifests. Passing `stable` does not turn an arbitrary
checkout into a release; release automation must select the released commit.
