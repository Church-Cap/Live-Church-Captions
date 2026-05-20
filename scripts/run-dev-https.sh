#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
  elif [ -f env.example ]; then
    cp env.example .env
  else
    echo "Could not find .env.example or env.example." >&2
    exit 1
  fi
fi
if [ ! -f certs/church-cap.pem ] || [ ! -f certs/church-cap-key.pem ]; then
  echo "Missing local certificate. Run: ./scripts/generate-local-cert.sh"
  echo "For trusted local testing on your Mac: ./scripts/generate-trusted-local-cert-macos.sh"
  exit 1
fi
python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8443}" \
  --ssl-certfile certs/church-cap.pem \
  --ssl-keyfile certs/church-cap-key.pem \
  --reload
