#!/bin/bash
#
# Verify that all managed version fields match the root VERSION file.
#
# Usage:
#   ./scripts/check-version-sync.sh

set -euo pipefail

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$STUDIO_ROOT"

if [ ! -f VERSION ]; then
  echo "ERROR: VERSION file not found at the Studio root."
  exit 1
fi

VERSION="$(tr -d '[:space:]' < VERSION)"
SEMVER_REGEX='^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'

if [[ ! "$VERSION" =~ $SEMVER_REGEX ]]; then
  echo "ERROR: VERSION must be a semver-like value (e.g. 1.2.3). Found: $VERSION"
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

# Backend workspace metadata. Both backend crates inherit this version, and the
# binary reports it at run time and in the OpenAPI document.
BACKEND_CARGO_VERSION="$(
  awk '
    /^\[/ { in_workspace_package = ($0 == "[workspace.package]") }
    in_workspace_package && /^version = "/ {
      v = $0
      sub(/^version = "/, "", v)
      sub(/"$/, "", v)
      print v
      exit
    }
  ' backend/Cargo.toml
)"
check_equals "backend/Cargo.toml [workspace.package] version" "$BACKEND_CARGO_VERSION" "$VERSION"

# Backend lock metadata
for backend_crate in junjo-backend junjo-evidence; do
  BACKEND_CARGO_LOCK_VERSION="$(
    awk -v name_line="name = \"$backend_crate\"" '
      $0 == name_line {
        getline
        gsub(/^version = "/, "", $0)
        gsub(/"$/, "", $0)
        print $0
        exit
      }
    ' backend/Cargo.lock
  )"
  check_equals "backend/Cargo.lock $backend_crate version" "$BACKEND_CARGO_LOCK_VERSION" "$VERSION"
done

# Ingestion package metadata
INGESTION_CARGO_VERSION="$(
  awk '
    /^version = "/ {
      v = $0
      sub(/^version = "/, "", v)
      sub(/"$/, "", v)
      print v
      exit
    }
  ' ingestion/Cargo.toml
)"
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
FRONTEND_PACKAGE_VERSION="$(
  awk '
    /"version": "/ {
      v = $0
      sub(/.*"version": "/, "", v)
      sub(/".*/, "", v)
      print v
      exit
    }
  ' frontend/package.json
)"
check_equals "frontend/package.json version" "$FRONTEND_PACKAGE_VERSION" "$VERSION"

FRONTEND_PACKAGE_LOCK_TOP_VERSION="$(
  awk '
    /"version": "/ {
      v = $0
      sub(/.*"version": "/, "", v)
      sub(/".*/, "", v)
      print v
      exit
    }
  ' frontend/package-lock.json
)"
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

# OpenAPI document exported by the backend (read by the frontend and SDK
# contract tests).
#
# Print the string at one key path of the document. A path that is absent or
# does not hold a string prints nothing, so it is reported as a mismatch.
openapi_string() {
  python3 - frontend/backend/openapi.json "$@" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as document:
    value = json.load(document)
for key in sys.argv[2:]:
    value = value.get(key) if isinstance(value, dict) else None
print(value if isinstance(value, str) else "")
PY
}

OPENAPI_INFO_VERSION="$(openapi_string info version)"
check_equals "frontend/backend/openapi.json info.version" "$OPENAPI_INFO_VERSION" "$VERSION"

OPENAPI_HEALTH_VERSION_DEFAULT="$(
  openapi_string components schemas HealthResponse properties version default
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
