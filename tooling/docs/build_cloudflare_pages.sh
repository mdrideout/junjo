#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repository_root"

if [[ -n "${CF_PAGES_BRANCH:-}" ]]; then
  if [[ "$CF_PAGES_BRANCH" == "docs-production" && "${JUNJO_DOCS_CHANNEL:-}" != "stable" ]]; then
    echo "Cloudflare production builds must use JUNJO_DOCS_CHANNEL=stable" >&2
    exit 1
  fi
  if [[ "$CF_PAGES_BRANCH" != "docs-production" && "${JUNJO_DOCS_CHANNEL:-next}" != "next" ]]; then
    echo "Cloudflare preview builds must use JUNJO_DOCS_CHANNEL=next" >&2
    exit 1
  fi
fi

required_uv_version="0.11.7"
if ! command -v uv >/dev/null 2>&1 || \
  [[ "$(uv --version)" != "uv ${required_uv_version} "* ]]; then
  python3 -m pip install --disable-pip-version-check "uv==${required_uv_version}"

  uv() {
    python3 -m uv "$@"
  }
fi

if [[ "$(uv --version)" != "uv ${required_uv_version} "* ]]; then
  echo "Required uv ${required_uv_version} is unavailable" >&2
  exit 1
fi

(
  cd sdks/python
  uv sync --frozen --package junjo --extra dev
  uv run sphinx-build -W -b html docs docs/_build/html
  uv run python docs/export_api.py baseline-check \
    --inventory docs/_build/html/objects.inv
)

(
  cd tooling/docs
  uv sync --frozen
  uv run python migrate_rst.py --check
)

(
  cd apps/website
  npm ci
  npm run docs:assemble
  npm run check
  npm run build
  npm run validate:build
  npm run docs:check
  npm audit --omit=dev --audit-level=high
)
