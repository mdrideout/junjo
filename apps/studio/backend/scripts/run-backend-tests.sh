#!/bin/bash
# Run all backend tests including gRPC integration tests
#
# Usage:
#   From backend directory:  ./scripts/run-backend-tests.sh
#   From repo root:          ./backend/scripts/run-backend-tests.sh

# Determine script directory and navigate to backend root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

echo "=========================================="
echo "Running All Backend Tests"
echo "=========================================="

# Set temp database paths
export JUNJO_SQLITE_PATH=/tmp/junjo-test-$(date +%s).db

echo "Using temp databases:"
echo "  SQLite: $JUNJO_SQLITE_PATH"
echo

# Track test results
UNIT_RESULT=0
INTEGRATION_RESULT=0
GRPC_RESULT=0

# Run unit tests (no server needed)
echo "=== Unit Tests ==="
uv run pytest -m "unit" -v || UNIT_RESULT=$?
echo

# Run integration tests without gRPC (no server needed)
echo "=== Integration Tests (no gRPC) ==="
uv run pytest -m "integration and not requires_grpc_server" -v || INTEGRATION_RESULT=$?
echo

# Run gRPC integration tests (requires server)
echo "=== gRPC Integration Tests ==="

# Check if required ports are available
PORT_1323_PID=$(lsof -ti :1323 2>/dev/null || true)
PORT_50053_PID=$(lsof -ti :50053 2>/dev/null || true)

if [ -n "$PORT_1323_PID" ] || [ -n "$PORT_50053_PID" ]; then
    echo ""
    echo "⚠️  Required ports are in use (needed for gRPC integration tests)"
    echo ""
    [ -n "$PORT_1323_PID" ] && echo "   Port 1323 (HTTP):  PID $PORT_1323_PID"
    [ -n "$PORT_50053_PID" ] && echo "   Port 50053 (gRPC): PID $PORT_50053_PID"
    echo ""
    echo "Options:"
    echo "  [k] Kill processes and continue"
    echo "  [s] Skip gRPC tests and continue"
    echo "  [q] Quit"
    echo ""
    read -p "Choice [k/s/q]: " choice
    case "$choice" in
        k|K)
            echo "Killing processes..."
            [ -n "$PORT_1323_PID" ] && kill -9 $PORT_1323_PID 2>/dev/null || true
            [ -n "$PORT_50053_PID" ] && kill -9 $PORT_50053_PID 2>/dev/null || true
            sleep 1  # Give OS time to release ports
            ;;
        s|S)
            echo "Skipping gRPC tests..."
            GRPC_RESULT=0  # Mark as passed (skipped)
            # Jump to summary by setting a flag
            SKIP_GRPC=1
            ;;
        *)
            echo "Exiting."
            exit 1
            ;;
    esac
fi

if [ "${SKIP_GRPC:-0}" != "1" ]; then
    echo "Running gRPC tests..."
    # We DO NOT start uvicorn here. The tests use the grpc_server_for_tests fixture
    # in backend/app/features/internal_auth/conftest.py to start an in-process
    # gRPC server that shares the isolated test database.
    #
    # If we started uvicorn here, it would use a different database connection
    # than the test fixture, causing tests to fail because they couldn't find
    # data (like API keys) that they just inserted into the fixture's DB.
    uv run pytest -m "requires_grpc_server" -v || GRPC_RESULT=$?
fi

# Summary
echo
echo "=========================================="
echo "Test Results Summary:"
echo "=========================================="
echo "Unit tests:        $([ $UNIT_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
echo "Integration tests: $([ $INTEGRATION_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
if [ "${SKIP_GRPC:-0}" = "1" ]; then
    echo "gRPC tests:        ⏭ SKIPPED (ports in use)"
else
    echo "gRPC tests:        $([ $GRPC_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
fi
echo "=========================================="

# Exit with error if critical tests failed
# (gRPC failures only count if tests were actually run)
if [ $UNIT_RESULT -ne 0 ]; then
    echo "❌ Critical tests failed"
    exit 1
fi

if [ "${SKIP_GRPC:-0}" != "1" ] && [ $GRPC_RESULT -ne 0 ]; then
    echo "❌ Critical tests failed"
    exit 1
fi

echo "✓ All critical tests passed!"
exit 0
