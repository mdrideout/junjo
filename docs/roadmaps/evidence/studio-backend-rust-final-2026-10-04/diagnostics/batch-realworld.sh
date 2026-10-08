#!/bin/bash
# Real-world runs: the real frontend in a browser and the real SDK querying
# while ingestion processes spans. One prototype image, four switch settings.
# Loaded host, split quota.
set -uo pipefail
B=/private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/bench9
cd "$B"
LOAD_IMAGE="${LOAD_IMAGE:-debian:bookworm-slim}"
BUSY='for i in 1 2 3 4; do while :; do :; done & done; wait'
stop_load() { docker rm -f junjo-rsmig-load >/dev/null 2>&1 || true; }
trap stop_load EXIT
# Let the host settle after the image build.
sleep "${SETTLE_SECONDS:-120}"
echo "== real-world runs, split quota, loaded host: $(date '+%H:%M:%S')"
stop_load
docker run -d --name junjo-rsmig-load --cpus 4 "$LOAD_IMAGE" sh -c "$BUSY" >/dev/null
sleep 5
python3 run.py rw "$@"
stop_load
echo "== done: $(date '+%H:%M:%S')"
