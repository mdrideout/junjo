#!/bin/sh

# ANSI color codes for a nice, colorful output
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Use printf for better compatibility and control over newlines
printf "${BOLD}${GREEN}\n"
printf "  ----------------------------------\n\n"
printf "  🎏 Junjo Server UI is running (Production) 🎏\n\n"
printf "  Use your production exposed hostname:port for access.\n\n"
printf "  ----------------------------------\n\n"
printf "${NC}"

# The main Nginx entrypoint will continue executing after this script.