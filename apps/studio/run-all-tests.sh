#!/bin/bash
# Run all tests across the entire Junjo AI Studio project
#
# This script runs:
#   0. Proto tool version checking (warns if mismatch)
#   1. Backend linting and formatting (cargo fmt check + clippy)
#   2. Backend tests (Rust; they build the ingestion binary)
#   3. Ingestion tests (Rust)
#   4. Frontend tests, lint, and production build
#   5. Contract tests (frontend ↔ backend schema validation)
#   6. OpenAPI document validation (export + staleness check)
#
# Usage:
#   ./run-all-tests.sh

set -e  # Exit on first error

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STUDIO_ROOT"

# Track test results
LINTING_RESULT=0
BACKEND_RESULT=0
FRONTEND_RESULT=0
CONTRACT_RESULT=0
OPENAPI_RESULT=0
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

# 1. Backend Linting and Formatting
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1/6: Backend Linting and Formatting (cargo fmt, clippy)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd backend
if cargo fmt --check && cargo clippy --all-targets --locked --quiet -- -D warnings; then
    echo "✅ Backend linting and formatting passed"
else
    echo "❌ Backend linting or formatting failed"
    echo ""
    echo "Run this to see detailed errors:"
    echo "  cd backend && cargo fmt --check"
    echo "  cd backend && cargo clippy --all-targets --locked -- -D warnings"
    echo ""
    LINTING_RESULT=1
fi
cd ..
echo ""

# 2. Backend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2/6: Backend Tests (Rust)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd backend
cargo test --locked || BACKEND_RESULT=$?
cd ..
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
# Written beside the document first, so a failed export never leaves a
# truncated document behind.
cargo run --quiet --locked --package junjo-backend -- openapi > ../frontend/backend/openapi.json.tmp
# The document is a committed file. Step 6 reports whether the one in the
# working tree already was what the backend exports.
if ! cmp -s ../frontend/backend/openapi.json.tmp ../frontend/backend/openapi.json; then
    OPENAPI_RESULT=1
fi
mv ../frontend/backend/openapi.json.tmp ../frontend/backend/openapi.json
cd ..
echo ""

# 4. Frontend Tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4/6: Frontend Tests, Lint, and Build (TypeScript)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd frontend
npm run test:run || FRONTEND_RESULT=$?
npm run lint || FRONTEND_RESULT=$?
npm run build || FRONTEND_RESULT=$?
cd ..
echo ""

# 5. Contract Tests (Schema Validation)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5/6: Contract Tests (Schema Validation)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./backend/scripts/validate_rest_api_contracts.sh || CONTRACT_RESULT=$?
echo ""

# 6. OpenAPI Document Validation
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6/6: OpenAPI Document Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $OPENAPI_RESULT -eq 0 ]; then
    echo "✅ OpenAPI document is up-to-date"
else
    echo "❌ OpenAPI document was not what the backend exports"
    echo ""
    echo "The export above replaced it. Review the difference as a contract change:"
    echo "  git diff -- frontend/backend/openapi.json"
    echo ""
fi
echo ""

# Summary
echo "=============================================="
echo "Test Results Summary"
echo "=============================================="
echo "Backend linting:   $([ $LINTING_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Backend tests:     $([ $BACKEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Ingestion tests:   $([ $INGESTION_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Frontend tests:    $([ $FRONTEND_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Contract tests:    $([ $CONTRACT_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "OpenAPI document:  $([ $OPENAPI_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "=============================================="

# Exit with error if any tests failed
if [ $LINTING_RESULT -ne 0 ] || [ $BACKEND_RESULT -ne 0 ] || [ $INGESTION_RESULT -ne 0 ] || [ $FRONTEND_RESULT -ne 0 ] || [ $CONTRACT_RESULT -ne 0 ] || [ $OPENAPI_RESULT -ne 0 ]; then
    echo "❌ Some tests failed"
    exit 1
fi

echo "✓ All tests passed!"
exit 0
