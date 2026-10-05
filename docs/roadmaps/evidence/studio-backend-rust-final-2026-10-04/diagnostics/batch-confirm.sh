#!/bin/bash
# Confirmation that the default image behaves as the measured pushdown variant.
# Interleaved with the earlier image, pushdown off and on. Loaded host.
set -uo pipefail
B=/private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/bench9
cd "$B"
LOAD_IMAGE="${LOAD_IMAGE:-debian:bookworm-slim}"
BUSY='for i in 1 2 3 4; do while :; do :; done & done; wait'
stop_load() { docker rm -f junjo-rsmig-load >/dev/null 2>&1 || true; }
trap stop_load EXIT
echo "== default-image confirmation, split quota, loaded host: $(date '+%H:%M:%S')"
stop_load
docker run -d --name junjo-rsmig-load --cpus 4 "$LOAD_IMAGE" sh -c "$BUSY" >/dev/null
sleep 5
python3 run.py confirm \
  rust:filtered:1 rust-pushdown:filtered:1 rust-default:filtered:1 \
  rust:filtered:2 rust-pushdown:filtered:2 rust-default:filtered:2 \
  rust:filtered:3 rust-pushdown:filtered:3 rust-default:filtered:3
stop_load
echo "== done: $(date '+%H:%M:%S')"
