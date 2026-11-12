#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The Apple Silicon engine must be built on macOS." >&2
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "The v0.9.0 macOS target requires an Apple Silicon (arm64) build host." >&2
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_PACKAGING_PYTHON="python3.12"
if [[ -x "$PROJECT_ROOT/.venv-packaging/bin/python" ]]; then
  DEFAULT_PACKAGING_PYTHON="$PROJECT_ROOT/.venv-packaging/bin/python"
fi
PACKAGING_PYTHON="${CHURCH_CAP_PACKAGING_PYTHON:-$DEFAULT_PACKAGING_PYTHON}"
if ! command -v "$PACKAGING_PYTHON" >/dev/null 2>&1; then
  echo "Python 3.12 was not found. Set CHURCH_CAP_PACKAGING_PYTHON to the Python 3.12 build interpreter." >&2
  exit 1
fi

PYTHON_VERSION="$("$PACKAGING_PYTHON" -c 'import platform; print(platform.python_version())')"
PYTHON_ARCH="$("$PACKAGING_PYTHON" -c 'import platform; print(platform.machine())')"
if [[ "$PYTHON_VERSION" != 3.12.* ]]; then
  echo "The packaging build requires Python 3.12; found $PYTHON_VERSION." >&2
  exit 1
fi
if [[ "$PYTHON_ARCH" != "arm64" ]]; then
  echo "The packaging interpreter must be arm64; found $PYTHON_ARCH." >&2
  exit 1
fi

echo "Apple Silicon packaging host ready: Python $PYTHON_VERSION ($PYTHON_ARCH)."
