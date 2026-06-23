#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This start script is intended for Linux." >&2
  exit 1
fi

VENV_PY="$APP_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "The local Python environment has not been set up yet." >&2
  echo "Run: bash setup-linux.sh" >&2
  exit 1
fi

if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
  elif [[ -f "env.example" ]]; then
    cp env.example .env
  else
    echo "Could not find .env.example or env.example." >&2
    exit 1
  fi
fi

VIEWER_PORT="${VIEWER_PORT:-8080}"
OPERATOR_PORT="${OPERATOR_PORT:-9090}"
LAN_IP="$("$VENV_PY" - <<'PY'
import socket
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("8.8.8.8", 80))
        print(sock.getsockname()[0])
except Exception:
    print("127.0.0.1")
PY
)"
OPERATOR_URL="http://localhost:${OPERATOR_PORT}/operator"
STARTUP_URL="http://localhost:${OPERATOR_PORT}/setup"
AUDIENCE_URL="http://${LAN_IP}:${VIEWER_PORT}/"

echo "Starting Church Cap in secure dual-port mode..."
echo "Operator page: $OPERATOR_URL"
echo "First-run password setup: $STARTUP_URL"
echo "Audience/IP URL: $AUDIENCE_URL"
echo ""
echo "Press Ctrl+C to stop Church Cap."

(
  for _ in {1..45}; do
    if command -v curl >/dev/null 2>&1 && curl -fsS -o /dev/null "$STARTUP_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$STARTUP_URL" >/dev/null 2>&1 || true
  fi
) &

exec "$VENV_PY" scripts/run-dual.py
