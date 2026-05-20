#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Church Cap bootstrap for macOS"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install it with: brew install python@3.12" >&2
  exit 1
fi

if command -v brew >/dev/null 2>&1; then
  echo "Checking PortAudio..."
  if ! brew list portaudio >/dev/null 2>&1; then
    brew install portaudio
  fi
else
  echo "Homebrew not found. If sounddevice fails later, install PortAudio manually."
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip "setuptools<82" wheel
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  elif [ -f env.example ]; then
    cp env.example .env
    echo "Created .env from env.example"
  else
    echo "Could not find .env.example or env.example." >&2
    exit 1
  fi
fi

mkdir -p data logs

echo "Done. Start with: ./scripts/run-dev.sh"
echo "Then open: http://localhost:9090/operator"
