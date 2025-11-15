#!/bin/sh

# Junjo AI Studio Frontend Production Startup Script
#
# Generates runtime configuration for the frontend production build.
# The production frontend is a static build served by nginx, so runtime
# configuration is injected via a JavaScript file that sets window.runtimeConfig.

# === Runtime Configuration ==========================================================
# API_HOST: Backend API URL
# - Development default: http://localhost:1323
# - Production: Use JUNJO_PROD_BACKEND_URL environment variable

# Validate JUNJO_ENV is set
if [ -z "$JUNJO_ENV" ]; then
  echo "ERROR: JUNJO_ENV must be set when using production build"
  echo "Set JUNJO_ENV=production or JUNJO_ENV=development in your .env file"
  exit 1
fi

if [ "$JUNJO_ENV" = "production" ]; then
  # Validate required production variables
  if [ -z "$JUNJO_PROD_FRONTEND_URL" ]; then
    echo "ERROR: JUNJO_PROD_FRONTEND_URL is required when JUNJO_ENV=production"
    echo "See .env.example for configuration details"
    exit 1
  fi

  if [ -z "$JUNJO_PROD_BACKEND_URL" ]; then
    echo "ERROR: JUNJO_PROD_BACKEND_URL is required when JUNJO_ENV=production"
    echo "See .env.example for configuration details"
    exit 1
  fi

  if [ -z "$JUNJO_PROD_INGESTION_URL" ]; then
    echo "ERROR: JUNJO_PROD_INGESTION_URL is required when JUNJO_ENV=production"
    echo "See .env.example for configuration details"
    exit 1
  fi

  # Use explicit URLs
  API_HOST="$JUNJO_PROD_BACKEND_URL"
  FRONTEND_URL="$JUNJO_PROD_FRONTEND_URL"
  INGESTION_URL="$JUNJO_PROD_INGESTION_URL"
else
  # Development defaults
  API_HOST="http://localhost:1323"
  FRONTEND_URL="http://localhost:5153"
  INGESTION_URL="grpc://localhost:50051"
fi

# Create the config file in the nginx web root
CONFIG_FILE="/usr/share/nginx/html/config.js"
echo "window.runtimeConfig = { API_HOST: \"${API_HOST}\" };" > $CONFIG_FILE

# === Startup Message ================================================================
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

printf "${BOLD}${GREEN}\n"
printf "  ----------------------------------\n\n"
printf "  🎏 Junjo AI Studio Frontend 🎏\n\n"
printf "  Environment: ${JUNJO_ENV}\n"
if [ "$JUNJO_ENV" = "production" ]; then
  printf "  Frontend URL: ${FRONTEND_URL}\n"
  printf "  Backend URL: ${API_HOST}\n"
  printf "  Ingestion URL: ${INGESTION_URL}\n"
else
  printf "  Frontend: ${FRONTEND_URL}\n"
  printf "  Backend API: ${API_HOST}\n"
fi
printf "\n  ----------------------------------\n\n"
printf "${NC}"

# The main Nginx entrypoint will continue executing after this script.
