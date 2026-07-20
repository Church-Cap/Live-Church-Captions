#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}" --proxy-headers --no-access-log
