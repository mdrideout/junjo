#!/bin/sh
# Record the production frontend container's memory. No ports are published,
# so the maintainer's own Studio stacks are not touched.
set -eu
IMAGE=junjo-rsmig-frontend:local
NAME=junjo-rsmig-frontend

measure() {
  label=$1
  shift
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --rm --name "$NAME" -e JUNJO_ENV=development "$@" "$IMAGE" >/dev/null
  sleep 20
  echo "== $label: idle after 20 s"
  docker stats --no-stream --format '{{.MemUsage}}' "$NAME"
  docker exec "$NAME" sh -c 'echo current=$(cat /sys/fs/cgroup/memory.current) peak=$(cat /sys/fs/cgroup/memory.peak); grep -E "^(anon|file|shmem) " /sys/fs/cgroup/memory.stat; echo nginx_workers=$(ps | grep "[n]ginx: worker" | wc -l)'
  docker exec "$NAME" sh -c 'i=0; while [ $i -lt 200 ]; do wget -q -O /dev/null http://127.0.0.1:26153/ && wget -q -O /dev/null http://127.0.0.1:26153/sign-in; i=$((i+1)); done'
  echo "== $label: after 400 page requests"
  docker stats --no-stream --format '{{.MemUsage}}' "$NAME"
  docker exec "$NAME" sh -c 'echo current=$(cat /sys/fs/cgroup/memory.current) peak=$(cat /sys/fs/cgroup/memory.peak); grep -E "^(anon|file|shmem) " /sys/fs/cgroup/memory.stat'
  docker rm -f "$NAME" >/dev/null
}

docker image inspect "$IMAGE" --format 'image={{.Id}} size={{.Size}}'
measure "one CPU visible" --cpuset-cpus 0
measure "all host CPUs visible"
