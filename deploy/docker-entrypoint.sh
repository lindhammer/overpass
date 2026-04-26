#!/bin/sh
set -eu

display="${DISPLAY:-:99}"
screen="${XVFB_SCREEN:-1280x1024x24}"
server_num="${display#:}"
server_num="${server_num%%.*}"
socket="/tmp/.X11-unix/X${server_num}"

Xvfb "$display" -screen 0 "$screen" -nolisten tcp -ac &
xvfb_pid=$!
cmd_pid=""

cleanup() {
    if [ -n "$cmd_pid" ]; then
        kill "$cmd_pid" 2>/dev/null || true
    fi
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
}

handle_signal() {
    cleanup
    exit 143
}

trap cleanup EXIT
trap handle_signal INT TERM

attempts=0
while [ ! -S "$socket" ]; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 50 ]; then
        echo "Xvfb did not create $socket" >&2
        exit 1
    fi
    sleep 0.1
done

export DISPLAY="$display"

set +e
"$@" &
cmd_pid=$!
wait "$cmd_pid"
status=$?
set -e

cmd_pid=""
cleanup
trap - EXIT
exit "$status"
