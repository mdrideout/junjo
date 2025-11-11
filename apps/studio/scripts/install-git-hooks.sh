#!/bin/bash
# Script to install Git hooks for Junjo AI Studio development

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Installing Junjo AI Studio Git hooks...${NC}"
echo ""

# Get the repository root
REPO_ROOT=$(git rev-parse --show-toplevel)

# Create hooks directory if it doesn't exist
mkdir -p "$REPO_ROOT/.git/hooks"

# Install pre-commit hook
echo "📝 Installing pre-commit hook..."
cp "$REPO_ROOT/scripts/pre-commit.sh" "$REPO_ROOT/.git/hooks/pre-commit"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"
echo -e "${GREEN}✓${NC} Pre-commit hook installed"

echo ""
echo -e "${GREEN}✓ Git hooks installation complete!${NC}"
echo ""
echo "The pre-commit hook will automatically:"
echo "  • Regenerate proto files before each commit"
echo "  • Stage updated proto files automatically"
echo "  • Prevent commits with stale proto code"
echo ""
echo "To uninstall, run: rm .git/hooks/pre-commit"
