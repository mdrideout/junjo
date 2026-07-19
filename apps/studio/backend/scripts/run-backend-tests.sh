#!/bin/bash
# Run the complete backend test collection, including gRPC integration tests.
#
# Usage:
#   From backend directory:  ./scripts/run-backend-tests.sh
#   From Studio root:        ./backend/scripts/run-backend-tests.sh

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

# Some gRPC fixtures bind this fixed test port. Check it before starting the
# single complete pytest run so an occupied port cannot produce a confusing
# partial failure late in the suite.
PORT_50053_PID=$(lsof -ti :50053 2>/dev/null || true)

if [ -n "$PORT_50053_PID" ]; then
    echo ""
    echo "⚠️  Required ports are in use (needed for gRPC integration tests)"
    echo ""
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
            [ -n "$PORT_50053_PID" ] && kill -9 $PORT_50053_PID 2>/dev/null || true
            sleep 1  # Give OS time to release ports
            ;;
        s|S)
            echo "Skipping gRPC tests..."
            SKIP_GRPC=1
            ;;
        *)
            echo "Exiting."
            exit 1
            ;;
    esac
fi

TEST_RESULT=0
if [ "${SKIP_GRPC:-0}" = "1" ]; then
    uv run pytest -m "not requires_grpc_server" -v || TEST_RESULT=$?
else
    uv run pytest -v || TEST_RESULT=$?
fi

echo
echo "=========================================="
echo "Test Results Summary:"
echo "=========================================="
echo "Backend collection: $([ $TEST_RESULT -eq 0 ] && echo '✓ PASSED' || echo '❌ FAILED')"
if [ "${SKIP_GRPC:-0}" = "1" ]; then
    echo "gRPC tests:         ⏭ SKIPPED (ports in use)"
else
    echo "gRPC tests:         included"
fi
echo "=========================================="

if [ $TEST_RESULT -ne 0 ]; then
    echo "❌ Backend tests failed"
    exit 1
fi

echo "✓ Backend test collection passed!"
exit 0
