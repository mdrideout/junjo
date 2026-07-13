#!/bin/bash
# Repository-level pre-commit entrypoint for independently owned components.

set -e

PLATFORM_ROOT=$(git rev-parse --show-toplevel)

"$PLATFORM_ROOT/apps/studio/scripts/pre-commit.sh"
