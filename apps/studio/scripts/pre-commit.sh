#!/bin/bash
# Pre-commit hook to check backend formatting
# This keeps unformatted backend code out of commits

set -e

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Resolve the Studio project independently from the platform Git root.
STUDIO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Function to check backend formatting
check_backend_format() {
  echo "🎨 Pre-commit: Running cargo fmt --check on backend..."
  cd "$STUDIO_ROOT/backend"

  # Check if cargo is available
  if ! command -v cargo &> /dev/null; then
    echo ""
    echo -e "${RED}❌ cargo not found. The backend format check cannot run.${NC}"
    echo "     Install with: https://rustup.rs"
    echo ""
    return 1
  fi

  # The toolchain pinned by backend/rust-toolchain.toml formats the code.
  if cargo fmt --check; then
    echo -e "  ${GREEN}✓${NC} Backend code is formatted"
    return 0
  else
    echo ""
    echo -e "${RED}❌ Backend formatting differences found!${NC}"
    echo ""
    echo "Please format the backend before committing."
    echo "Run: cd backend && cargo fmt"
    echo ""
    return 1
  fi
}

# Run the format check
if ! check_backend_format; then
  exit 1  # Fail commit if the backend is not formatted
fi

# Return to the Studio root
cd "$STUDIO_ROOT"

exit 0
