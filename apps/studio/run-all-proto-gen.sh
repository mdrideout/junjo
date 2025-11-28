#!/bin/bash
# Regenerate all protocol buffer files for Go and Python
#
# Usage: ./run-all-proto-gen.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "========================================"
echo "Regenerating All Proto Files"
echo "========================================"
echo ""

# Go protos (ingestion service)
echo "Regenerating Go proto files..."
cd ingestion
make proto
cd ..
echo "✅ Go proto files regenerated"
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
