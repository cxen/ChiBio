#!/bin/bash
# Safely stop the ChiBio gunicorn server listening on :PORT (default 5000).
#
# WHY THIS EXISTS: on 2026-07-17 an ad-hoc `ss -ltnp | grep -o 'pid=[0-9]*' | kill`
# with no port filter SIGTERM'd EVERY listener on the board (systemd pid 1, sshd,
# nginx, dnsmasq, node) and wedged it until a physical power-cycle. The lesson is
# not "filter better next time" -- it is "never hand-roll the kill". This script
# refuses to signal any pid that is not a `gunicorn` process, and never touches
# pid 1, so its worst failure mode is doing nothing, never taking the box down.
# Always stop the server with `./cb-stop.sh`; never with a raw ss|kill pipe.
set -u

# True only for a gunicorn process that is safe to stop. pid 1 and anything whose
# /proc/<pid>/comm is not exactly "gunicorn" is rejected -- this is the guard.
gunicorn_pid() {
  local pid="$1"
  [ "$pid" = "1" ] && return 1
  [ -r "/proc/$pid/comm" ] || return 1
  [ "$(cat "/proc/$pid/comm")" = "gunicorn" ] || return 1
  return 0
}

listener_pids() {
  # ss associates the listening socket on :$1 with its owning pids.
  ss -ltnp "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

cmd="${1:-stop}"
port="${2:-5000}"

case "$cmd" in
  self-check)
    # pid 1 is systemd, never gunicorn -> must be refused. Fails loudly if the guard rots.
    if gunicorn_pid 1; then echo "SELF-CHECK FAILED: guard would kill pid 1" >&2; exit 1; fi
    echo "self-check OK: guard refuses pid 1 (systemd)"
    ;;
  stop)
    pids="$(listener_pids "$port")"
    [ -z "$pids" ] && { echo "No listener on :$port -- nothing to stop."; exit 0; }
    # Validate the WHOLE batch before signalling anything: if any listener on the
    # port is not gunicorn, abort without killing a single process.
    for pid in $pids; do
      gunicorn_pid "$pid" || {
        echo "REFUSING to stop :$port -- pid $pid is $(cat "/proc/$pid/comm" 2>/dev/null), not gunicorn. Killed nothing." >&2
        exit 1
      }
    done
    for pid in $pids; do
      echo "Stopping gunicorn pid $pid (cwd $(readlink "/proc/$pid/cwd" 2>/dev/null))"
      kill "$pid"
    done
    ;;
  *)
    echo "usage: $0 [stop|self-check] [port]" >&2
    exit 2
    ;;
esac
