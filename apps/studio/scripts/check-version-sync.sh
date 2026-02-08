#!/bin/bash
#
# Verify that all managed version fields match the root VERSION file.
#
# Usage:
#   ./scripts/check-version-sync.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f VERSION ]; then
  echo "ERROR: VERSION file not found at repo root."
  exit 1
fi

VERSION="$(tr -d '[:space:]' < VERSION)"
SEMVER_REGEX='^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'

if [[ ! "$VERSION" =~ $SEMVER_REGEX ]]; then
  echo "ERROR: VERSION must be a semver-like value (e.g. 0.80.0). Found: $VERSION"
  exit 1
fi

FAILURES=0

check_equals() {
  local name="$1"
  local actual="$2"
  local expected="$3"

  if [ "$actual" != "$expected" ]; then
    echo "FAIL $name: expected '$expected', found '$actual'"
    FAILURES=$((FAILURES + 1))
  else
    echo "OK   $name: $actual"
  fi
}

# Backend package metadata
BACKEND_PYPROJECT_VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' backend/pyproject.toml | head -n 1)"
check_equals "backend/pyproject.toml [project].version" "$BACKEND_PYPROJECT_VERSION" "$VERSION"

# Backend runtime/API metadata
BACKEND_MAIN_FASTAPI_VERSIONS_RAW="$(sed -n 's/.*version="\([^"]*\)".*/\1/p' backend/app/main.py)"
BACKEND_MAIN_FASTAPI_VERSION_COUNT="$(printf "%s\n" "$BACKEND_MAIN_FASTAPI_VERSIONS_RAW" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "$BACKEND_MAIN_FASTAPI_VERSION_COUNT" -lt 2 ]; then
  echo "FAIL backend/app/main.py expected at least 2 version=\"...\" values"
  FAILURES=$((FAILURES + 1))
else
  i=0
  while IFS= read -r main_version; do
    if [ -z "$main_version" ]; then
      continue
    fi
    i=$((i + 1))
    check_equals \
      "backend/app/main.py version=\"...\" entry $i" \
      "$main_version" \
      "$VERSION"
  done <<< "$BACKEND_MAIN_FASTAPI_VERSIONS_RAW"
fi

BACKEND_MAIN_ROOT_VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' backend/app/main.py | head -n 1)"
check_equals "backend/app/main.py root response version" "$BACKEND_MAIN_ROOT_VERSION" "$VERSION"

BACKEND_HEALTH_SCHEMA_VERSION_DEFAULT="$(
  sed -n 's/.*version: str = Field(default="\([^"]*\)".*/\1/p' backend/app/common/responses.py | head -n 1
)"
check_equals \
  "backend/app/common/responses.py HealthResponse.version default" \
  "$BACKEND_HEALTH_SCHEMA_VERSION_DEFAULT" \
  "$VERSION"

# Backend lock metadata
BACKEND_UV_LOCK_VERSION="$(
  awk '
    $0 ~ /^name = "junjo-backend"$/ {
      getline
      gsub(/^version = "/, "", $0)
      gsub(/"$/, "", $0)
      print $0
      exit
    }
  ' backend/uv.lock
)"
check_equals "backend/uv.lock package version" "$BACKEND_UV_LOCK_VERSION" "$VERSION"

# Ingestion package metadata
INGESTION_CARGO_VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' ingestion/Cargo.toml | head -n 1)"
check_equals "ingestion/Cargo.toml package version" "$INGESTION_CARGO_VERSION" "$VERSION"

# Ingestion lock metadata
INGESTION_CARGO_LOCK_VERSION="$(
  awk '
    $0 ~ /^name = "ingestion"$/ {
      getline
      gsub(/^version = "/, "", $0)
      gsub(/"$/, "", $0)
      print $0
      exit
    }
  ' ingestion/Cargo.lock
)"
check_equals "ingestion/Cargo.lock package version" "$INGESTION_CARGO_LOCK_VERSION" "$VERSION"

# Frontend package metadata
FRONTEND_PACKAGE_VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' frontend/package.json | head -n 1)"
check_equals "frontend/package.json version" "$FRONTEND_PACKAGE_VERSION" "$VERSION"

FRONTEND_PACKAGE_LOCK_TOP_VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' frontend/package-lock.json | head -n 1)"
check_equals "frontend/package-lock.json top-level version" "$FRONTEND_PACKAGE_LOCK_TOP_VERSION" "$VERSION"

FRONTEND_PACKAGE_LOCK_ROOT_VERSION="$(
  awk '
    /"packages":[[:space:]]*\{/ { in_packages = 1; next }
    in_packages && /"":[[:space:]]*\{/ { in_root = 1; next }
    in_root && /"version":[[:space:]]*"/ {
      gsub(/.*"version":[[:space:]]*"/, "", $0)
      gsub(/".*/, "", $0)
      print $0
      exit
    }
  ' frontend/package-lock.json
)"
check_equals "frontend/package-lock.json packages[\"\"] version" "$FRONTEND_PACKAGE_LOCK_ROOT_VERSION" "$VERSION"

# Generated OpenAPI schema version (copied into frontend for contract tests)
OPENAPI_INFO_VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' frontend/backend/openapi.json | head -n 1)"
check_equals "frontend/backend/openapi.json info.version" "$OPENAPI_INFO_VERSION" "$VERSION"

OPENAPI_HEALTH_VERSION_DEFAULT="$(
  awk '
    /"title": "Version"/ { in_version_schema = 1; next }
    in_version_schema && /"default": "/ {
      gsub(/.*"default": "/, "", $0)
      gsub(/".*/, "", $0)
      print $0
      exit
    }
  ' frontend/backend/openapi.json
)"
check_equals \
  "frontend/backend/openapi.json HealthResponse.version default" \
  "$OPENAPI_HEALTH_VERSION_DEFAULT" \
  "$VERSION"

if [ "$FAILURES" -ne 0 ]; then
  echo ""
  echo "Version sync check failed with $FAILURES issue(s)."
  echo "Run: ./scripts/sync-version.sh $VERSION"
  exit 1
fi

echo ""
echo "Version sync check passed for $VERSION"
