#!/usr/bin/env bash
# Start/stop the split shell: engine on loopback, UI on the LAN.
#
#   scripts/serve.sh up      start both (idempotent; prints the login URL)
#   scripts/serve.sh down    stop both
#   scripts/serve.sh status  show what is running
#
# Deliberately not a supervisor: on a single box with limited memory this is a
# manual switch. Wire `up` to a dashboard button if you want a one-click entry;
# a browser page on its own cannot start a server, something local must run it.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
STATE_DIR="${TRADINGAGENTS_HOME:-$HOME/.tradingagents}/web"
ENGINE_PORT="${TRADINGAGENTS_ENGINE_PORT:-8502}"
UI_PORT="${TRADINGAGENTS_UI_PORT:-8501}"
ENGINE_PID="$STATE_DIR/engine.pid"
UI_PID="$STATE_DIR/ui.pid"
ENGINE_LOG="$STATE_DIR/engine.log"
UI_LOG="$STATE_DIR/ui.log"

mkdir -p "$STATE_DIR"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

healthy() { [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$1")" = "200" ]; }

running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

start_engine() {
  if healthy "http://127.0.0.1:$ENGINE_PORT/healthz"; then
    echo "engine already up on :$ENGINE_PORT"; return 0
  fi
  # detach from this shell's session: the script exits, the server must not
  setsid nohup "$PY" -m tradingagents_web --role engine --port "$ENGINE_PORT" \
    >"$ENGINE_LOG" 2>&1 < /dev/null &
  echo $! >"$ENGINE_PID"
}

start_ui() {
  if healthy "http://127.0.0.1:$UI_PORT/healthz"; then
    echo "ui already up on :$UI_PORT"; return 0
  fi
  setsid nohup "$PY" -m tradingagents_web --role ui --port "$UI_PORT" \
    --engine "http://127.0.0.1:$ENGINE_PORT" >"$UI_LOG" 2>&1 < /dev/null &
  echo $! >"$UI_PID"
}

await_health() {
  local url="$1" name="$2"
  for _ in $(seq 1 40); do
    healthy "$url" && { echo "$name ready"; return 0; }
    sleep 0.5
  done
  echo "$name did not become healthy; see $STATE_DIR/${name}.log" >&2
  return 1
}

cmd_up() {
  start_engine || return 1
  await_health "http://127.0.0.1:$ENGINE_PORT/healthz" engine || return 1
  start_ui || return 1
  await_health "http://127.0.0.1:$UI_PORT/healthz" ui || return 1
  local token="${TRADINGAGENTS_WEB_TOKEN:-}"
  echo
  echo "打开： http://$(hostname -I | awk '{print $1}'):$UI_PORT/login?token=$token"
}

cmd_down() {
  for name in ui engine; do
    local pidfile="$STATE_DIR/$name.pid"
    if running "$pidfile"; then
      kill "$(cat "$pidfile")" 2>/dev/null && echo "$name stopped"
      rm -f "$pidfile"
    else
      echo "$name not running"
      rm -f "$pidfile"
    fi
  done
  # shutdown is graceful: wait for both ports to close before returning, or the
  # next `up` sees a healthy socket and skips starting the new code
  for _ in $(seq 1 20); do
    if ! healthy "http://127.0.0.1:$ENGINE_PORT/healthz" \
       && ! healthy "http://127.0.0.1:$UI_PORT/healthz"; then
      return 0
    fi
    sleep 0.25
  done
}

cmd_status() {
  healthy "http://127.0.0.1:$ENGINE_PORT/healthz" && echo "engine  up  :$ENGINE_PORT" \
    || echo "engine  down"
  healthy "http://127.0.0.1:$UI_PORT/healthz" && echo "ui      up  :$UI_PORT" \
    || echo "ui      down"
}

case "${1:-up}" in
  up) cmd_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  *) echo "usage: $0 {up|down|status}" >&2; exit 2 ;;
esac
