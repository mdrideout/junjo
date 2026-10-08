#!/bin/bash
# Runs the repository's real-world test for several builds, one after another,
# on a host whose other load is held constant by four busy loops.
# Usage: batch.sh <variant>:<rate>:<rep> ...   rate is standard or heavy.
set -uo pipefail
T=/private/tmp/claude-501/-Users-matt-repos-junjo/7906a453-730b-42d4-82b0-9d62cfc7a17a/scratchpad/rw-tool
R=/Users/matt/repos/junjo/apps/studio/ingestion/benchmarks
BUSY='for i in 1 2 3 4; do while :; do :; done & done; wait'
stop_load() { docker rm -f junjo-rsmig-load >/dev/null 2>&1 || true; }
free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }
trap stop_load EXIT
# Let the host settle after an image build.
sleep "${SETTLE_SECONDS:-120}"
echo "== real-world runs with the repository tool, loaded host: $(date '+%H:%M:%S')"
stop_load
docker run -d --name junjo-rsmig-load --cpus 4 debian:bookworm-slim sh -c "$BUSY" >/dev/null
sleep 5
cd "$R"
for job in "$@"; do
  IFS=: read -r variant rate rep <<< "$job"
  interval=100
  [ "$rate" = heavy ] && interval=25
  label="$variant-$rate-$rep"
  echo "START $label $(date '+%H:%M:%S')"
  JUNJO_BENCHMARK_PROJECT_NAME=junjo-rsmig-bench \
  JUNJO_BENCHMARK_COMPOSE_OVERLAY="$T/overlay-$variant.yaml" \
    uv run python real_world.py --skip-build --label "$label" --export-interval-ms "$interval" \
      --backend-port "$(free_port)" --ingestion-port "$(free_port)" \
      --output "$T/results/$label.json" > "$T/results/$label.report.md" 2> "$T/results/$label.stderr"
  echo "END $label exit=$? $(date '+%H:%M:%S')"
done
stop_load
echo "== done: $(date '+%H:%M:%S')"
