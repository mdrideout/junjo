#!/bin/bash
# Run all tests across the entire Junjo AI Studio project
#
# This script runs:
#   1. Backend tests (unit, integration, gRPC)
#   2. Frontend tests (unit, integration, component)
#   3. Contract tests (frontend ↔ backend schema validation)
#   4. Proto file validation
#
# Usage:
#   ./run-all-tests.sh

set -e  # Exit on first error

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Track test results
BACKEND_RESULT=0
FRONTEND_RESULT=0
CONTRACT_RESULT=0
PROTO_RESULT=0

echo "=============================================="
echo "Running All Junjo AI Studio Tests"
echo "=============================================="
echo ""

# 1. Backend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1/4: Backend Tests (Python)"
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

# 2. Frontend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2/4: Frontend Tests (TypeScript)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd frontend
npm run test:run || FRONTEND_RESULT=$?
cd ..
echo ""

# 3. Contract Tests (Schema Validation)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3/4: Contract Tests (Schema Validation)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/ci_validate_schemas.sh || CONTRACT_RESULT=$?
echo ""

# 4. Proto File Validation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4/4: Proto File Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Regenerating Go proto files..."
cd ingestion
make proto > /dev/null 2>&1
cd ..

echo "Regenerating Python proto files..."
cd backend
./scripts/generate_proto.sh > /dev/null 2>&1
cd ..

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
echo "Backend tests:     $([ $BACKEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Frontend tests:    $([ $FRONTEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Contract tests:    $([ $CONTRACT_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Proto validation:  $([ $PROTO_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "=============================================="

# Exit with error if any tests failed
if [ $BACKEND_RESULT -ne 0 ] || [ $FRONTEND_RESULT -ne 0 ] || [ $CONTRACT_RESULT -ne 0 ] || [ $PROTO_RESULT -ne 0 ]; then
    echo "❌ Some tests failed"
    exit 1
fi

echo "✓ All tests passed!"
exit 0
