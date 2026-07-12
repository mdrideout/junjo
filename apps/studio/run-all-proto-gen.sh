#!/bin/bash
# Regenerate all protocol buffer files for Python (backend).
# Rust ingestion generates proto code at build time via build.rs.
#
# Usage: ./run-all-proto-gen.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "========================================"
echo "Regenerating All Proto Files"
echo "========================================"
echo ""

# Rust protos (ingestion service)
echo "Rust ingestion protos are generated at build time via ingestion/build.rs (no committed files)."
echo ""

# Python protos (backend service)
echo "Regenerating Python proto files..."
cd backend
./scripts/generate_proto.sh
cd ..
echo "✅ Python proto files regenerated"
echo ""

echo "========================================"
echo "✅ All proto files regenerated"
echo "========================================"
