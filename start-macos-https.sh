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
if [[ ! -f certs/church-cap.pem ]] || [[ ! -f certs/church-cap-key.pem ]]; then
  echo "Missing HTTPS certificate. Run one of:"
  echo "  ./scripts/generate-trusted-local-cert-macos.sh"
  echo "  ./scripts/generate-local-cert.sh"
  exit 1
fi
PORT="${PORT:-8443}"
VENV_PY="$APP_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Could not find .venv/bin/python. Run: ./setup-macos.sh" >&2
  exit 1
fi
OPERATOR_URL="https://localhost:${PORT}/operator"
echo "Starting Church Cap with HTTPS..."
echo "Operator page: $OPERATOR_URL"
echo "Note: phones will warn unless they trust the certificate authority."
(
  sleep 2
  open "$OPERATOR_URL" >/dev/null 2>&1 || true
) &
exec "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --ssl-certfile certs/church-cap.pem --ssl-keyfile certs/church-cap-key.pem
