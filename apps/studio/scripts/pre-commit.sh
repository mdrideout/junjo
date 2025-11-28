#!/bin/bash
# Pre-commit hook to auto-generate proto files
# This ensures proto files are always up-to-date before committing

set -e

echo "🔄 Pre-commit: Regenerating proto files..."

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the repository root
REPO_ROOT=$(git rev-parse --show-toplevel)

# Track if any proto files were modified
PROTO_MODIFIED=false

# Required tool versions (must match PROTO_VERSIONS.md)
REQUIRED_PROTOC_VERSION="30.2"
REQUIRED_PROTOC_GEN_GO_VERSION="v1.36.10"
REQUIRED_PROTOC_GEN_GO_GRPC_VERSION="1.5.1"

# Function to check tool versions
check_tool_versions() {
  local version_mismatch=false

  # Check protoc version
  if command -v protoc &> /dev/null; then
    local protoc_version=$(protoc --version | awk '{print $2}')
    if [ "$protoc_version" != "$REQUIRED_PROTOC_VERSION" ]; then
      echo -e "${YELLOW}⚠️  Warning: protoc version mismatch${NC}"
      echo "     Expected: v${REQUIRED_PROTOC_VERSION}"
      echo "     Found:    v${protoc_version}"
      version_mismatch=true
    fi
  fi

  # Check protoc-gen-go version
  if command -v protoc-gen-go &> /dev/null; then
    local protoc_gen_go_version=$(protoc-gen-go --version 2>&1 | awk '{print $2}')
    if [ "$protoc_gen_go_version" != "$REQUIRED_PROTOC_GEN_GO_VERSION" ]; then
      echo -e "${YELLOW}⚠️  Warning: protoc-gen-go version mismatch${NC}"
      echo "     Expected: ${REQUIRED_PROTOC_GEN_GO_VERSION}"
      echo "     Found:    ${protoc_gen_go_version}"
      version_mismatch=true
    fi
  fi

  # Check protoc-gen-go-grpc version
  if command -v protoc-gen-go-grpc &> /dev/null; then
    local protoc_gen_go_grpc_version=$(protoc-gen-go-grpc --version 2>&1 | awk '{print $2}')
    if [ "$protoc_gen_go_grpc_version" != "$REQUIRED_PROTOC_GEN_GO_GRPC_VERSION" ]; then
      echo -e "${YELLOW}⚠️  Warning: protoc-gen-go-grpc version mismatch${NC}"
      echo "     Expected: ${REQUIRED_PROTOC_GEN_GO_GRPC_VERSION}"
      echo "     Found:    ${protoc_gen_go_grpc_version}"
      version_mismatch=true
    fi
  fi

  if [ "$version_mismatch" = true ]; then
    echo ""
    echo -e "${YELLOW}📚 To install correct versions, see: PROTO_VERSIONS.md${NC}"
    echo ""
  fi
}

# Check versions before generating
check_tool_versions

# Function to generate Go proto files for ingestion
generate_go_proto() {
  echo "  → Generating Go proto files for ingestion..."
  cd "$REPO_ROOT/ingestion"

  # Check if protoc is available
  if ! command -v protoc &> /dev/null; then
    echo -e "${YELLOW}⚠️  Warning: protoc not found. Skipping Go proto generation.${NC}"
    echo "     See PROTO_VERSIONS.md for installation instructions"
    return 1
  fi

  # Check if Go plugins are available
  if ! command -v protoc-gen-go &> /dev/null || ! command -v protoc-gen-go-grpc &> /dev/null; then
    echo -e "${YELLOW}⚠️  Warning: Go protobuf plugins not found. Skipping Go proto generation.${NC}"
    echo "     See PROTO_VERSIONS.md for installation instructions"
    return 1
  fi

  # Generate proto files
  make proto > /dev/null 2>&1

  # Check if any files were modified
  if ! git diff --quiet proto_gen/; then
    PROTO_MODIFIED=true
    git add proto_gen/
    echo -e "  ${GREEN}✓${NC} Go proto files regenerated and staged"
  else
    echo "  ✓ Go proto files already up-to-date"
  fi

  # Verify no orphaned schemas (missing .proto source files)
  echo "  → Verifying proto schemas..."
  if make proto-check-orphans > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Proto schema verification passed"
  else
    echo -e "  ${RED}❌ Orphaned proto schemas detected!${NC}"
    echo ""
    make proto-check-orphans  # Show detailed output
    echo ""
    echo -e "${YELLOW}Fix: Restore missing .proto files or run 'cd ingestion && make proto-clean'${NC}"
    return 1
  fi
}

# Function to generate Python proto files for backend
generate_python_proto() {
  echo "  → Generating Python proto files for backend..."
  cd "$REPO_ROOT/backend"

  # Check if the generation script exists
  if [ ! -f "scripts/generate_proto.sh" ]; then
    echo -e "${YELLOW}⚠️  Warning: generate_proto.sh not found. Skipping Python proto generation.${NC}"
    return 1
  fi

  # Generate proto files
  ./scripts/generate_proto.sh > /dev/null 2>&1

  # Check if any files were modified
  if ! git diff --quiet app/proto_gen/; then
    PROTO_MODIFIED=true
    git add app/proto_gen/
    echo -e "  ${GREEN}✓${NC} Python proto files regenerated and staged"
  else
    echo "  ✓ Python proto files already up-to-date"
  fi
}

# Run proto generation for both services
generate_go_proto || true      # Continue even if Go proto generation fails
generate_python_proto || true  # Continue even if Python proto generation fails

# Track if any Python files were formatted
PYTHON_FORMATTED=false

# Function to run ruff format and check on backend
run_ruff_format() {
  echo ""
  echo "🎨 Pre-commit: Running ruff format on backend..."
  cd "$REPO_ROOT/backend"

  # Check if uv is available
  if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}⚠️  Warning: uv not found. Skipping ruff format.${NC}"
    echo "     Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 1
  fi

  # Run ruff format to auto-format files
  uv run ruff format app/ > /dev/null 2>&1

  # Check if any files were modified
  if ! git diff --quiet app/; then
    PYTHON_FORMATTED=true
    git add app/
    echo -e "  ${GREEN}✓${NC} Python files formatted and staged"
  else
    echo "  ✓ Python files already formatted"
  fi
}

# Function to run ruff check on backend
run_ruff_check() {
  echo ""
  echo "🔍 Pre-commit: Running ruff check on backend..."
  cd "$REPO_ROOT/backend"

  # Check if uv is available
  if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}⚠️  Warning: uv not found. Skipping ruff check.${NC}"
    return 1
  fi

  # Run ruff check
  if uv run ruff check app/ --quiet; then
    echo -e "  ${GREEN}✓${NC} All linting checks passed"
    return 0
  else
    echo ""
    echo -e "${RED}❌ Ruff linting errors found!${NC}"
    echo ""
    echo "Please fix the linting errors above before committing."
    echo "Run: cd backend && uv run ruff check app/"
    echo ""
    return 1
  fi
}

# Run ruff format and check
run_ruff_format || true  # Continue even if format fails
if ! run_ruff_check; then
  exit 1  # Fail commit if linting errors exist
fi

# Summary
echo ""
if [ "$PROTO_MODIFIED" = true ] || [ "$PYTHON_FORMATTED" = true ]; then
  if [ "$PROTO_MODIFIED" = true ]; then
    echo -e "${GREEN}✓ Proto files regenerated and staged for commit${NC}"
  fi
  if [ "$PYTHON_FORMATTED" = true ]; then
    echo -e "${GREEN}✓ Python files formatted and staged for commit${NC}"
  fi
else
  echo -e "✓ All files are up-to-date"
fi

# Return to repo root
cd "$REPO_ROOT"

exit 0
