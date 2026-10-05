#!/bin/bash
# The measured batch: constant host load in a sibling container for every run.
set -uo pipefail
B=/private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/bench9
cd "$B"
LOAD_IMAGE="${LOAD_IMAGE:-alpine:3.22}"
BUSY='for i in 1 2 3 4; do while :; do :; done & done; wait'
stop_load() { docker rm -f junjo-rsmig-load >/dev/null 2>&1 || true; }
trap stop_load EXIT

echo "== split quota, loaded host: $(date '+%H:%M:%S')"
stop_load
docker run -d --name junjo-rsmig-load --cpus 4 "$LOAD_IMAGE" sh -c "$BUSY" >/dev/null
sleep 5
python3 run.py load \
  python:mixed:1 rust:mixed:1 python:mixed:2 rust:mixed:2 python:mixed:3 rust:mixed:3 \
  python:saturation:1 rust:saturation:1 python:saturation:2 rust:saturation:2 python:saturation:3 rust:saturation:3 \
  rust:filtered:1 rust-pushdown:filtered:1 python:filtered:1 \
  rust:filtered:2 rust-pushdown:filtered:2 python:filtered:2 \
  rust:filtered:3 rust-pushdown:filtered:3
stop_load

echo "== single CPU, load pinned away from CPU 0: $(date '+%H:%M:%S')"
docker run -d --name junjo-rsmig-load --cpuset-cpus 4-7 "$LOAD_IMAGE" sh -c "$BUSY" >/dev/null
sleep 5
python3 run.py load \
  python-shared:mixed:1 rust-shared:mixed:1 python-shared:mixed:2 rust-shared:mixed:2 \
  python-shared:saturation:1 rust-shared:saturation:1 python-shared:saturation:2 rust-shared:saturation:2
stop_load
echo "== done: $(date '+%H:%M:%S')"
