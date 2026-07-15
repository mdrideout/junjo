# Python documentation ownership

This directory is the canonical source for Python SDK documentation. The public
site is rendered by Starlight, but Python narrative content, API extraction,
examples, and migration evidence remain owned and validated here.

This is a migration, not a rewrite:

- `*.rst` remains the migration source until the unified site passes the
  accepted cutover gates.
- `content/` is a mechanical Markdown export. Do not edit it directly; change
  the matching RST source and rerun the converter.
- `api-sphinx-baseline.json` records the complete warning-strict Sphinx object
  inventory.
- `export_api.py` statically extracts the same public surface with Griffe's
  automatic Sphinx/Google/NumPy docstring parsing and emits Starlight Markdown.
  Generated API pages are staged outside this component and are never committed
  here.
- Sphinx stays in CI until the legacy site is retired after measured parity and
  rollback windows.

## Local validation

From `sdks/python`:

```bash
uv sync --frozen --extra dev
uv run sphinx-build -W -b html docs docs/_build/html
uv run python docs/export_api.py baseline-check \
  --inventory docs/_build/html/objects.inv
```

Only refresh the committed baseline after reviewing an intentional public API
change:

```bash
uv run python docs/export_api.py baseline \
  --inventory docs/_build/html/objects.inv \
  --output docs/api-sphinx-baseline.json
```

From the repository root, validate the narrative migration and assemble the
public site:

```bash
uv sync --project tooling/docs --frozen
uv run --project tooling/docs python tooling/docs/migrate_rst.py --check
python3 tooling/docs/assemble_public_docs.py --write
npm --prefix apps/website run validate
```

Use `migrate_rst.py --write` only when the RST sources intentionally changed.
The content ledger will update source and target hashes so review can prove
that every source document remains accounted for.

Assembly defaults to the `next` documentation channel and labels generated API
pages as source previews. Build `stable` only from the exact released checkout:

```bash
JUNJO_DOCS_CHANNEL=stable python3 tooling/docs/assemble_public_docs.py --write
```

The version in `pyproject.toml`, full source revision, and channel are embedded
in the API and assembly manifests. Passing `stable` does not turn an arbitrary
checkout into a release; release automation must select the released commit.
