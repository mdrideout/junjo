#!/bin/sh

# Keep the development container alive until cargo-watch has finished
# forwarding shutdown to the ingestion process and that process has exited.
shutdown_requested=0
watch_pid=""
watch_status=0

forward_shutdown() {
    shutdown_requested=1
    if [ -n "$watch_pid" ] && kill -0 "$watch_pid" 2>/dev/null; then
        kill -INT "$watch_pid"
    fi
}

ingestion_is_running() {
    for process_name in /proc/[0-9]*/comm; do
        if [ -r "$process_name" ] && [ "$(cat "$process_name")" = "ingestion" ]; then
            return 0
        fi
    done
    return 1
}

trap forward_shutdown INT TERM

cargo watch \
    -i .dbdata \
    -i target \
    -w src \
    -w /proto \
    -w Cargo.toml \
    -w build.rs \
    -x run &
watch_pid=$!

while kill -0 "$watch_pid" 2>/dev/null; do
    wait "$watch_pid"
    watch_status=$?
done

if [ "$shutdown_requested" -eq 1 ]; then
    while ingestion_is_running; do
        sleep 0.05
    done
    exit 0
fi

exit "$watch_status"
