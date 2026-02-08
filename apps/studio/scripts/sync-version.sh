#!/bin/bash
#
# Sync all managed version fields from the root VERSION file (or an explicit version).
#
# Usage:
#   ./scripts/sync-version.sh            # uses VERSION file
#   ./scripts/sync-version.sh 0.80.0     # sets VERSION, then syncs everything

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SEMVER_REGEX='^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'

if [ "$#" -gt 1 ]; then
  echo "Usage: ./scripts/sync-version.sh [version]"
  exit 1
fi

if [ "$#" -eq 1 ]; then
  VERSION="$1"
  if [[ ! "$VERSION" =~ $SEMVER_REGEX ]]; then
    echo "ERROR: Invalid version '$VERSION' (expected semver-like value, e.g. 0.80.0)"
    exit 1
  fi
  printf "%s\n" "$VERSION" > VERSION
else
  if [ ! -f VERSION ]; then
    echo "ERROR: VERSION file not found at repo root."
    exit 1
  fi
  VERSION="$(tr -d '[:space:]' < VERSION)"
  if [[ ! "$VERSION" =~ $SEMVER_REGEX ]]; then
    echo "ERROR: VERSION file is invalid ('$VERSION')."
    exit 1
  fi
fi

echo "Syncing repository version to $VERSION"

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
perl -i -pe 's/^version = "[^"]+"/version = "'"$VERSION"'"/ if /^version = "/' backend/pyproject.toml
perl -i -pe 's/version="[^"]+"/version="'"$VERSION"'"/g' backend/app/main.py
perl -i -pe 's/"version": "[^"]+"/"version": "'"$VERSION"'"/g' backend/app/main.py
perl -i -pe 's/(version: str = Field\(default=")[^"]+(")/${1}'"$VERSION"'${2}/' backend/app/common/responses.py
perl -0777 -i -pe 's/(name = "junjo-backend"\nversion = ")[^"]+(")/${1}'"$VERSION"'${2}/s' backend/uv.lock

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
perl -i -pe 's/^version = "[^"]+"/version = "'"$VERSION"'"/ if /^version = "/' ingestion/Cargo.toml
perl -0777 -i -pe 's/(name = "ingestion"\nversion = ")[^"]+(")/${1}'"$VERSION"'${2}/s' ingestion/Cargo.lock

# ---------------------------------------------------------------------------
# Frontend package metadata (updates package.json + package-lock.json)
# ---------------------------------------------------------------------------
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required to sync frontend package version."
  exit 1
fi

(
  cd frontend
  npm version "$VERSION" --no-git-tag-version --allow-same-version >/dev/null
)

# ---------------------------------------------------------------------------
# Generated OpenAPI schema copy used by frontend contract tests
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required to regenerate backend OpenAPI schema."
  exit 1
fi

(
  cd backend
  uv run python scripts/export_openapi_schema.py >/dev/null
)
cp backend/openapi.json frontend/backend/openapi.json

# Final verification
./scripts/check-version-sync.sh

echo ""
echo "Done. Version synchronized to $VERSION"
