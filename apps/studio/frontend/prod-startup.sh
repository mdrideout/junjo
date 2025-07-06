#!/bin/sh

# This script is responsible for two things:
# 1. Generating a runtime configuration file for the frontend.
# 2. Displaying a startup message.

# === Runtime Configuration ====================================================
# The frontend is a static build, so we can't use build-time environment
# variables for configuration that needs to change at runtime. Instead, we
# create a JavaScript file that sets a global configuration object.

# Default API_HOST to localhost for development environments.
API_HOST="http://localhost:1323"

# If running in production, construct the API host from the auth domain.
if [ "$JUNJO_ENV" = "production" ]; then
  if [ -n "$JUNJO_PROD_AUTH_DOMAIN" ]; then
    API_HOST="https://api.${JUNJO_PROD_AUTH_DOMAIN}"
  fi
fi

# Create the config file in the web root.
# This path is based on the `COPY --from=builder /app/dist /usr/share/nginx/html`
# command in the Dockerfile.
CONFIG_FILE="/usr/share/nginx/html/config.js"
echo "window.runtimeConfig = { API_HOST: \"${API_HOST}\" };" > $CONFIG_FILE

# === Startup Message ==========================================================
# ANSI color codes for a nice, colorful output
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Use printf for better compatibility and control over newlines
printf "${BOLD}${GREEN}\n"
printf "  ----------------------------------\n\n"
printf "  🎏 Junjo Server UI is running (Production) 🎏\n\n"
printf "  API_HOST: ${API_HOST}\n\n"
printf "  ----------------------------------\n\n"
printf "${NC}"

# The main Nginx entrypoint will continue executing after this script.