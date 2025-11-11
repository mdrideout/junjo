#!/bin/sh

echo "[DEBUG] --- Running entrypoint.sh ---"

# Only run migrations if RUN_MIGRATIONS is true
if [ "$RUN_MIGRATIONS" = "true" ]; then
  # Run Alembic migrations
  echo "Running Alembic migrations..."
  if ! alembic upgrade head; then
      echo "Migration failed."
      exit 1
  fi
fi

# Execute the command passed to the script
echo "Executing command: $@"
exec "$@"
