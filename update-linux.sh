#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
export CHURCH_CAP_UPDATE_START_SCRIPT="start-linux.sh"
export CHURCH_CAP_UPDATE_SETUP_SCRIPT="setup-linux.sh"
exec /usr/bin/env bash "$APP_DIR/update-macos.sh" "$@"
