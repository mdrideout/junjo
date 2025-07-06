#!/bin/bash

# This script reads a domain from a .env file, then downloads the specific
# server certificate for that domain and its wildcard subdomain by finding
# the correct certificate in the chain based on its Common Name (CN).

# --- Configuration ---
ENV_FILE=".env"
OUTPUT_DIR="tmp/certs"
# ---------------------

# Function to download a certificate chain and extract a specific certificate by its CN
get_cert_by_cn() {
  local CONNECT_HOST="$1"
  local TARGET_CN="$2"
  local OUTPUT_DIR="$3"
  local FILENAME="$4"
  local PORT=443

  echo "--------------------------------------------------"
  echo "Downloading certificate for CN '$TARGET_CN' (connecting to $CONNECT_HOST)..."

  # Use openssl to get the full certificate chain details
  local cert_chain_data
  cert_chain_data=$(openssl s_client -showcerts -servername "$CONNECT_HOST" -connect "$CONNECT_HOST:$PORT" < /dev/null 2>&1)

  echo ""
  echo "--- Full Certificate Response for $CONNECT_HOST ---"
  echo "$cert_chain_data"
  echo "-------------------------------------------"
  
  if [ -z "$cert_chain_data" ]; then
    echo "Error: No data received from openssl for $CONNECT_HOST. Is the server running?"
    return 1
  fi

  # Use awk to find the certificate block corresponding to the TARGET_CN
  # and extract the PEM-formatted certificate.
  local server_cert
  server_cert=$(echo "$cert_chain_data" | awk -v cn_to_find="s:CN=$TARGET_CN" '
    # When we find the line with the correct CN, set a flag.
    index($0, cn_to_find) {
      found_cn = 1
    }
    # When we find the BEGIN line AND the flag is set, start printing.
    /-----BEGIN CERTIFICATE-----/ {
      if (found_cn) {
        printing = 1
      }
    }
    # If we are in printing mode, print the line.
    printing {
      print
    }
    # If we are printing and we hit the END line, print it and exit.
    printing && /-----END CERTIFICATE-----/ {
      exit
    }
  ')

  if [ -z "$server_cert" ]; then
      echo "Error: Could not find certificate with CN '$TARGET_CN' for host $CONNECT_HOST."
      return 1
  fi

  # Save the extracted server certificate to the specified file
  echo "$server_cert" > "${OUTPUT_DIR}/${FILENAME}"

  echo "Success! Server certificate for CN '$TARGET_CN' saved to '${OUTPUT_DIR}/${FILENAME}'."
}

# --- Main Script ---

# Check if the .env file exists
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: The '$ENV_FILE' file was not found in the current directory."
  exit 1
fi

# Create the base output directory
mkdir -p "$OUTPUT_DIR"
echo "Certificates will be saved in the '$OUTPUT_DIR' directory."

# Read the JUNJO_PROD_AUTH_DOMAIN from the .env file and strip quotes
DOMAIN=$(grep '^JUNJO_PROD_AUTH_DOMAIN=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')

if [ -z "$DOMAIN" ]; then
  echo "Error: JUNJO_PROD_AUTH_DOMAIN is not set in the '$ENV_FILE' file."
  exit 1
fi

echo "Found domain: $DOMAIN"

# Download the server certificate for the root domain by matching its CN
get_cert_by_cn "$DOMAIN" "$DOMAIN" "$OUTPUT_DIR" "$DOMAIN.pem"

# Download the server certificate for the wildcard subdomain by matching its CN
get_cert_by_cn "api.$DOMAIN" "*.$DOMAIN" "$OUTPUT_DIR" "_$DOMAIN.pem"

echo "--------------------------------------------------"
echo "Script finished."