#!/bin/sh

# Keep the development container alive until cargo-watch has finished
# forwarding shutdown to the backend process and that process has exited, so
# the backend stops its indexer and checkpoints its databases.
shutdown_requested=0
watch_pid=""
watch_status=0

forward_shutdown() {
    shutdown_requested=1
    if [ -n "$watch_pid" ] && kill -0 "$watch_pid" 2>/dev/null; then
        kill -INT "$watch_pid"
    fi
}

backend_is_running() {
    for process_name in /proc/[0-9]*/comm; do
        if [ -r "$process_name" ] && [ "$(cat "$process_name")" = "junjo-backend" ]; then
            return 0
        fi
    done
    return 1
}

trap forward_shutdown INT TERM

# The compiler needs several GB of memory. Under a container memory limit it
# is killed, and the build log does not say why.
memory_limit=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
if [ -n "$memory_limit" ] && [ "$memory_limit" != "max" ]; then
    echo "WARNING: this container has a memory limit of ${memory_limit} bytes." >&2
    echo "Compiling the backend needs several GB. If the compiler is killed, set the" >&2
    echo "JUNJO_BACKEND_* limits in .env as .env.example does for a development build." >&2
fi

cargo watch \
    -i target \
    -w server \
    -w evidence \
    -w schema \
    -w /app/proto \
    -w Cargo.toml \
    -x "run --locked --package junjo-backend" &
watch_pid=$!

while kill -0 "$watch_pid" 2>/dev/null; do
    wait "$watch_pid"
    watch_status=$?
done

if [ "$shutdown_requested" -eq 1 ]; then
    while backend_is_running; do
        sleep 0.05
    done
    exit 0
fi

exit "$watch_status"
