#!/bin/bash
# Run all tests across the entire Junjo AI Studio project
#
# This script runs:
#   0. Proto tool version checking (warns if mismatch)
#   1. Python linting (ruff check)
#   2. Backend tests (unit, integration, gRPC)
#   3. Frontend tests (unit, integration, component)
#   4. Contract tests (frontend ↔ backend schema validation)
#   5. Proto file validation (regeneration, orphan detection, staleness check)
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
echo "1/5: Python Linting (ruff)"
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
echo "2/5: Backend Tests (Python)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/run-backend-tests.sh || BACKEND_RESULT=$?
echo ""

# Regenerate OpenAPI schema before frontend tests
# (Frontend contract tests import this schema)
echo "Regenerating OpenAPI schema for frontend tests..."
cd backend
uv run python scripts/export_openapi_schema.py > /dev/null 2>&1
cp openapi.json ../frontend/backend/openapi.json
cd ..
echo ""

# 3. Frontend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3/5: Frontend Tests (TypeScript)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd frontend
npm run test:run || FRONTEND_RESULT=$?
cd ..
echo ""

# 4. Contract Tests (Schema Validation)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4/5: Contract Tests (Schema Validation)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/validate_rest_api_contracts.sh || CONTRACT_RESULT=$?
echo ""

# 5. Proto File Validation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5/5: Proto File Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Regenerating Go proto files..."
cd ingestion
make proto > /dev/null 2>&1
cd ..

echo "Regenerating Python proto files..."
cd backend
./scripts/generate_proto.sh > /dev/null 2>&1
cd ..

echo "Checking for orphaned proto schemas..."
cd ingestion
if make proto-check-orphans > /dev/null 2>&1; then
    echo "✅ No orphaned proto schemas detected"
else
    echo "❌ Orphaned proto schemas detected"
    echo ""
    make proto-check-orphans  # Show detailed output
    PROTO_RESULT=1
fi
cd ..
echo ""

echo "Checking for uncommitted proto changes..."
if git diff --quiet -- 'proto/' 'ingestion/proto_gen/' 'backend/app/proto_gen/'; then
    echo "✅ Proto files are up-to-date"
else
    echo "❌ Proto files have uncommitted changes"
    git diff --name-only -- 'proto/' 'ingestion/proto_gen/' 'backend/app/proto_gen/'
    PROTO_RESULT=1
fi
echo ""

# Summary
echo "=============================================="
echo "Test Results Summary"
echo "=============================================="
echo "Python linting:    $([ $LINTING_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Backend tests:     $([ $BACKEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Frontend tests:    $([ $FRONTEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Contract tests:    $([ $CONTRACT_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Proto validation:  $([ $PROTO_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "=============================================="

# Exit with error if any tests failed
if [ $LINTING_RESULT -ne 0 ] || [ $BACKEND_RESULT -ne 0 ] || [ $FRONTEND_RESULT -ne 0 ] || [ $CONTRACT_RESULT -ne 0 ] || [ $PROTO_RESULT -ne 0 ]; then
    echo "❌ Some tests failed"
    exit 1
fi

echo "✓ All tests passed!"
exit 0
