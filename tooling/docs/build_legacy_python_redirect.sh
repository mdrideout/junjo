#!/usr/bin/env bash
set -euo pipefail

# Do not retire the Sphinx site until the unified Python landing page is live.
unified_docs_url="${JUNJO_UNIFIED_PYTHON_DOCS_URL:-https://junjo.ai/docs/python/}"
curl \
  --fail \
  --silent \
  --show-error \
  --output /dev/null \
  --retry 40 \
  --retry-all-errors \
  --retry-delay 15 \
  --max-time 10 \
  "$unified_docs_url"
