#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Church Cap factory reset"
echo ""
echo "This removes the operator account, all settings, saved transcripts, logs, exports,"
echo "and downloaded caption/voice models. It does not uninstall Church Cap."
echo "Stop Church Cap before continuing. Deleted data cannot be recovered."
echo ""
read -r -p "Type RESET to continue: " confirmation
if [[ "$confirmation" != "RESET" ]]; then
  echo "Factory reset cancelled."
  exit 1
fi

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then PYTHON_BIN="python3"; fi
"$PYTHON_BIN" scripts/factory-reset.py --confirm RESET
