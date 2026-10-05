#!/bin/bash
# Validate the REST contract between the backend and its consumers.
#
# 1. Export the OpenAPI document from the backend binary.
# 2. Write it where the frontend and the SDK contract tests read it.
# 3. Run the frontend contract tests against it.
#
# The exported document is a committed file. A change in it is a contract
# change and is reviewed as one.
#
# Usage, from any directory:
#   ./backend/scripts/validate_rest_api_contracts.sh
#
# Exit codes:
#   0 - validation passed
#   1 - validation failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$(cd "$BACKEND_DIR/../frontend" && pwd)"
CONTRACT="$FRONTEND_DIR/backend/openapi.json"

echo "========================================"
echo "REST contract validation"
echo "========================================"
echo ""

echo "Step 1: Exporting the OpenAPI document from the backend..."
cd "$BACKEND_DIR"
# Written beside the contract first, so a failed export never leaves a
# truncated contract behind.
cargo run --quiet --locked --package junjo-backend -- openapi > "$CONTRACT.tmp"
mv "$CONTRACT.tmp" "$CONTRACT"

echo ""
echo "Step 2: Running the frontend contract tests..."
cd "$FRONTEND_DIR"
npm run test:contracts

echo ""
echo "========================================"
echo "REST contract validation passed"
echo "========================================"
