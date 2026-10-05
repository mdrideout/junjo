#!/bin/bash
#
# Sync all managed version fields from the root VERSION file (or an explicit version).
#
# Usage:
#   ./scripts/sync-version.sh            # uses VERSION file
#   ./scripts/sync-version.sh 1.2.3      # sets VERSION, then syncs everything

set -euo pipefail

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"

SEMVER_REGEX='^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'

if [ "$#" -gt 1 ]; then
  echo "Usage: ./scripts/sync-version.sh [version]"
  exit 1
fi

if [ "$#" -eq 1 ]; then
  VERSION="$1"
  if [[ ! "$VERSION" =~ $SEMVER_REGEX ]]; then
    echo "ERROR: Invalid version '$VERSION' (expected semver-like value, e.g. 1.2.3)"
    exit 1
  fi
  printf "%s\n" "$VERSION" > VERSION
else
  if [ ! -f VERSION ]; then
    echo "ERROR: VERSION file not found at the Studio root."
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
# Backend (a Cargo workspace: both crates inherit [workspace.package] version)
# ---------------------------------------------------------------------------
perl -i -pe '
  $in_workspace_package = ($_ eq "[workspace.package]\n") if /^\[/;
  s/^version = "[^"]+"/version = "'"$VERSION"'"/ if $in_workspace_package;
' backend/Cargo.toml
perl -0777 -i -pe 's/(name = "junjo-backend"\nversion = ")[^"]+(")/${1}'"$VERSION"'${2}/s' backend/Cargo.lock
perl -0777 -i -pe 's/(name = "junjo-evidence"\nversion = ")[^"]+(")/${1}'"$VERSION"'${2}/s' backend/Cargo.lock

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
# OpenAPI document exported by the backend, read by the frontend and SDK
# contract tests
# ---------------------------------------------------------------------------
if ! command -v cargo >/dev/null 2>&1; then
  echo "ERROR: cargo is required to regenerate the backend OpenAPI document."
  exit 1
fi

# Written beside the document first, so a failed export never leaves a
# truncated document behind.
(
  cd backend
  cargo run --quiet --locked --package junjo-backend -- openapi > ../frontend/backend/openapi.json.tmp
)
mv frontend/backend/openapi.json.tmp frontend/backend/openapi.json

# Final verification
./scripts/check-version-sync.sh

echo ""
echo "Done. Version synchronized to $VERSION"
