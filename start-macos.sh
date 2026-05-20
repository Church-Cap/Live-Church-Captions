#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [[ ! -d ".venv" ]]; then
  echo "The local Python environment has not been set up yet."
  echo "Run: ./setup-macos.sh"
  exit 1
fi

if [[ ! -f ".env" ]]; then
  cp .env.example .env
fi

VIEWER_PORT="${VIEWER_PORT:-8080}"
OPERATOR_PORT="${OPERATOR_PORT:-9090}"
LOCALHOST_NAME="$(scutil --get LocalHostName 2>/dev/null || true)"
LAN_IP="$(python3 - <<'PY'
import socket
try:
    s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()
except Exception:
    print('127.0.0.1')
PY
)"
if [[ -n "$LOCALHOST_NAME" ]]; then
  AUDIENCE_URL="http://${LOCALHOST_NAME}.local:${VIEWER_PORT}/"
else
  AUDIENCE_URL="http://${LAN_IP}:${VIEWER_PORT}/"
fi
AUDIENCE_IP_URL="http://${LAN_IP}:${VIEWER_PORT}/"
OPERATOR_URL="http://localhost:${OPERATOR_PORT}/operator"

VENV_PY="$APP_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Could not find .venv/bin/python. Run: ./setup-macos.sh" >&2
  exit 1
fi

echo "Starting Church Cap in secure dual-port mode..."
echo "Operator page: $OPERATOR_URL"
echo "Audience hostname URL: $AUDIENCE_URL"
echo "Android/IP fallback URL: $AUDIENCE_IP_URL"
echo ""
echo "Please wait while Church Cap starts. The operator page will open automatically in a few seconds."
echo "If a browser tab shows localhost:${VIEWER_PORT}/operator, use the operator link above instead."
echo "If you are locked out, stop the server with Ctrl+C and run: ./reset-operator-password.sh"
echo "To inspect the stored login state, run: python3 scripts/diagnose-auth.py"
echo "Press Ctrl+C in this Terminal window to stop the server."

(
  for _ in {1..45}; do
    if curl -fsS -o /dev/null "$OPERATOR_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  open "$OPERATOR_URL" >/dev/null 2>&1 || true
) &

exec "$VENV_PY" scripts/run-dual.py
