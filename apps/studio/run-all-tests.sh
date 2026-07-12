#!/bin/bash
# Run all tests across the entire Junjo AI Studio project
#
# This script runs:
#   0. Proto tool version checking (warns if mismatch)
#   1. Python linting (ruff check)
#   2. Backend tests (unit, integration, gRPC)
#   3. Ingestion tests (Rust)
#   4. Frontend tests (unit, integration, component)
#   5. Contract tests (frontend ↔ backend schema validation)
#   6. Proto file validation (regeneration + staleness check)
#
# Usage:
#   ./run-all-tests.sh

set -e  # Exit on first error

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Track test results
LINTING_RESULT=0
BACKEND_RESULT=0
FRONTEND_RESULT=0
CONTRACT_RESULT=0
PROTO_RESULT=0
INGESTION_RESULT=0

echo "=============================================="
echo "Running All Junjo AI Studio Tests"
echo "=============================================="
echo ""

# Check proto tool versions (warn only, don't fail)
echo "Checking proto tool versions..."
REQUIRED_PROTOC_VERSION="30.2"
PROTOC_VERSION=$(protoc --version 2>&1 | awk '{print $2}')

if [ "$PROTOC_VERSION" != "$REQUIRED_PROTOC_VERSION" ]; then
    echo "⚠️  Warning: protoc version mismatch"
    echo "    Expected: $REQUIRED_PROTOC_VERSION"
    echo "    Found:    $PROTOC_VERSION"
    echo "    See PROTO_VERSIONS.md for installation instructions"
    echo ""
else
    echo "✓ protoc version correct ($PROTOC_VERSION)"
fi
echo ""

# 1. Python Linting
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1/6: Python Linting (ruff)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd backend
if uv run ruff check app/ --quiet; then
    echo "✅ Python linting passed"
else
    echo "❌ Python linting failed"
    echo ""
    echo "Run this to see detailed errors:"
    echo "  cd backend && uv run ruff check app/"
    echo ""
    LINTING_RESULT=1
fi
cd ..
echo ""

# 2. Backend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2/6: Backend Tests (Python)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/run-backend-tests.sh || BACKEND_RESULT=$?
echo ""

# 3. Ingestion Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3/6: Ingestion Tests (Rust)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ingestion
cargo test --locked || INGESTION_RESULT=$?
cd ..
echo ""

# Regenerate OpenAPI schema before frontend tests
# (Frontend contract tests import this schema)
echo "Regenerating OpenAPI schema for frontend tests..."
cd backend
uv run python scripts/export_openapi_schema.py > /dev/null 2>&1
cp openapi.json ../frontend/backend/openapi.json
cd ..
echo ""

# 4. Frontend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4/6: Frontend Tests (TypeScript)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd frontend
npm run test:run || FRONTEND_RESULT=$?
cd ..
echo ""

# 5. Contract Tests (Schema Validation)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5/6: Contract Tests (Schema Validation)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/validate_rest_api_contracts.sh || CONTRACT_RESULT=$?
echo ""

# 6. Proto File Validation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6/6: Proto File Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Regenerating Python proto files..."
cd backend
./scripts/generate_proto.sh > /dev/null 2>&1
cd ..
echo ""

echo "Checking for uncommitted proto changes..."
if git diff --quiet -- 'proto/' 'backend/app/proto_gen/'; then
    echo "✅ Proto files are up-to-date"
else
    echo "❌ Proto files have uncommitted changes"
    git diff --name-only -- 'proto/' 'backend/app/proto_gen/'
    PROTO_RESULT=1
fi
echo ""

# Summary
echo "=============================================="
echo "Test Results Summary"
echo "=============================================="
echo "Python linting:    $([ $LINTING_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Backend tests:     $([ $BACKEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Ingestion tests:   $([ $INGESTION_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Frontend tests:    $([ $FRONTEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Contract tests:    $([ $CONTRACT_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Proto validation:  $([ $PROTO_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "=============================================="

# Exit with error if any tests failed
if [ $LINTING_RESULT -ne 0 ] || [ $BACKEND_RESULT -ne 0 ] || [ $INGESTION_RESULT -ne 0 ] || [ $FRONTEND_RESULT -ne 0 ] || [ $CONTRACT_RESULT -ne 0 ] || [ $PROTO_RESULT -ne 0 ]; then
    echo "❌ Some tests failed"
    exit 1
fi

echo "✓ All tests passed!"
exit 0
