#!/bin/sh
# Generate Python code from Protocol Buffer definitions
# This script uses grpc_tools.protoc to generate both message classes and gRPC stubs
#
# Usage:
#   ./generate_proto.sh [OUTPUT_DIR] [PROTO_SOURCE_DIR]
#
# Defaults:
#   OUTPUT_DIR: ./app/proto_gen (relative to script's parent directory)
#   PROTO_SOURCE_DIR: ../proto (relative to script's parent directory)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Allow overriding directories (for Docker)
OUTPUT_DIR="${1:-$PROJECT_ROOT/app/proto_gen}"
PROTO_DIR="${2:-$(cd "$PROJECT_ROOT/../proto" && pwd)}"

# Detect Python command (uv for local, python for Docker with active venv)
if command -v uv > /dev/null 2>&1 && [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
    PYTHON_CMD="uv run python"
else
    PYTHON_CMD="python"
fi

echo "Generating Python protobuf code..."
echo "  Proto source: $PROTO_DIR"
echo "  Output directory: $OUTPUT_DIR"
echo "  Python command: $PYTHON_CMD"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate Python code from proto files
$PYTHON_CMD -m grpc_tools.protoc \
  -I"$PROTO_DIR" \
  --python_out="$OUTPUT_DIR" \
  --grpc_python_out="$OUTPUT_DIR" \
  "$PROTO_DIR"/*.proto

# Fix imports to use relative imports (required for Python package imports)
# Handle both macOS (sed -i '') and Linux (sed -i) syntax
for file in "$OUTPUT_DIR"/*_grpc.py; do
  if [ -f "$file" ]; then
    # Try macOS sed first, fall back to Linux sed
    sed -i '' 's/^import \([a-z_]*\)_pb2 as/from . import \1_pb2 as/g' "$file" 2>/dev/null || \
    sed -i 's/^import \([a-z_]*\)_pb2 as/from . import \1_pb2 as/g' "$file"
  fi
done

# Create __init__.py for Python package
touch "$OUTPUT_DIR/__init__.py"

echo "✓ Proto generation complete!"
echo "  Generated files:"
ls -1 "$OUTPUT_DIR"/*.py 2>/dev/null | xargs -n 1 basename || echo "  (no files generated)"
