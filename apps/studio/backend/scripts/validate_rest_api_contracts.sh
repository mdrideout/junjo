#!/bin/bash
# CI/CD script to validate API schemas
#
# This script:
# 1. Exports the OpenAPI schema from the FastAPI app
# 2. Copies OpenAPI schema to frontend for contract tests
# 3. Runs frontend contract tests to validate Zod schemas match OpenAPI
#
# Usage:
#   From backend directory:  ./scripts/validate_rest_api_contracts.sh
#   From repo root:          ./backend/scripts/validate_rest_api_contracts.sh
#
# Exit codes:
#   0 - Validation passed
#   1 - Validation failed

set -e  # Exit on first error

# Determine script directory and navigate to backend root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

echo "========================================"
echo "API Schema Validation (CI/CD)"
echo "========================================"
echo ""

# Step 1: Export OpenAPI schema from FastAPI
echo "Step 1: Exporting OpenAPI schema from backend..."
uv run python scripts/export_openapi_schema.py

# Step 2: Copy to frontend (so tests can import it)
echo ""
echo "Step 2: Copying OpenAPI schema to frontend..."
cp openapi.json ../frontend/backend/openapi.json

# Step 3: Run frontend contract tests
echo ""
echo "Step 3: Running frontend contract tests..."
cd ../frontend
npm run test:contracts

echo ""
echo "========================================"
echo "✅ Schema validation completed successfully"
echo "Backend and frontend schemas are in sync!"
echo "========================================"
