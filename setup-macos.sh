#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Church Cap"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BREW_BIN="/opt/homebrew/bin/brew"
PYTHON_BIN="/opt/homebrew/bin/python3.12"
DEFAULT_LOCALHOST="church-cap"

cd "$APP_DIR"

repair_script_permissions() {
  chmod +x setup-macos.sh start-macos.sh start-macos-https.sh setup-linux.sh start-linux.sh update-linux.sh reset-operator-password.sh fix-permissions.sh update-macos.sh 2>/dev/null || true
  chmod +x scripts/*.sh 2>/dev/null || true
  chmod +x scripts/*.py 2>/dev/null || true
}

repair_script_permissions

cat <<'INTRO'

=====================================================
 Church Cap first-time setup for Apple Silicon
=====================================================

This script will prepare this folder as a local server app.

It will check/install these system tools with Homebrew:
  - Homebrew itself, if missing
  - python@3.12
  - portaudio, required by the microphone/audio-interface package
  - optional: mkcert, only if you choose local trusted HTTPS testing

It will install Python packages ONLY into this project folder:
  - .venv/bin/python
  - .venv/lib/...

It will not install Python packages into the global/system Python.

Commands this script may run:
  chmod +x setup-macos.sh start-macos.sh start-macos-https.sh reset-operator-password.sh fix-permissions.sh update-macos.sh scripts/*.sh scripts/*.py
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
  brew install python@3.12 portaudio
  /opt/homebrew/bin/python3.12 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip "setuptools<82" wheel
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m pip install -r requirements-translation.txt
  ./scripts/install-translation-models-argos.sh                      # installs Base packs, does not enable live translation
  ./scripts/install-small100-core.sh                                 # optional heavier Core model
  sudo scutil --set ComputerName "Church Cap"      (optional)
  sudo scutil --set LocalHostName "church-cap"     (optional)
  sudo scutil --set HostName "church-cap.local"    (optional)

Nothing is published online. The caption server runs locally on this Mac.
INTRO

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script is intended for macOS." >&2
  exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: this script is tuned for Apple Silicon Macs. Detected: $(uname -m)" >&2
fi

read -r -p "Continue with setup? [y/N] " answer
case "${answer:-}" in
  y|Y|yes|YES) ;;
  *) echo "Setup cancelled."; exit 0 ;;
esac

step() { echo ""; echo "==> $1"; }

create_env_if_missing() {
  if [[ -f ".env" ]]; then
    echo ".env already exists; keeping your current settings."
    return
  fi
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    echo "Created .env from .env.example"
    return
  fi
  if [[ -f "env.example" ]]; then
    cp env.example .env
    echo "Created .env from env.example"
    return
  fi
  echo "Could not find .env.example or env.example. Re-download Church Cap and try again." >&2
  exit 1
}

step "1/7 Checking Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  if [[ -x "$BREW_BIN" ]]; then
    eval "$("$BREW_BIN" shellenv)"
  fi
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to install Python 3.12 and PortAudio."
  read -r -p "Install Homebrew now using the official installer? [y/N] " brew_answer
  case "${brew_answer:-}" in
    y|Y|yes|YES)
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      ;;
    *)
      echo "Homebrew installation skipped. Install it from https://brew.sh and run this again." >&2
      exit 1
      ;;
  esac
fi

if [[ -x "$BREW_BIN" ]]; then
  eval "$("$BREW_BIN" shellenv)"
  if ! grep -q '/opt/homebrew/bin/brew shellenv' "$HOME/.zprofile" 2>/dev/null; then
    echo "Adding Homebrew to ~/.zprofile for future Terminal windows."
    {
      echo ''
      echo '# Homebrew for Apple Silicon'
      echo 'eval "$(/opt/homebrew/bin/brew shellenv)"'
    } >> "$HOME/.zprofile"
  fi
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew still is not available on PATH. Open a new Terminal and rerun setup-macos.sh." >&2
  exit 1
fi

step "2/7 Installing/checking Homebrew packages"
echo "Required packages: python@3.12 portaudio"
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
brew list portaudio >/dev/null 2>&1 || brew install portaudio

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Could not find Homebrew Python 3.12." >&2
  exit 1
fi

echo "Using Python: $($PYTHON_BIN --version) at $PYTHON_BIN"

step "3/7 Creating local project virtual environment"
if [[ ! -d ".venv" ]]; then
  "$PYTHON_BIN" -m venv .venv
else
  echo ".venv already exists; reusing it. To rebuild, delete .venv and rerun setup."
fi

VENV_PY="$APP_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtual environment Python was not created correctly." >&2
  exit 1
fi

step "4/7 Installing Python packages inside .venv only"
"$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$VENV_PY" -m pip install --upgrade pip "setuptools<82" wheel
"$VENV_PY" -m pip install -r requirements.txt

step "5/7 Creating local folders and .env"
mkdir -p data logs certs
create_env_if_missing

step "6/7 Bonjour/mDNS hostname"
CURRENT_LOCALHOST="$(scutil --get LocalHostName 2>/dev/null || true)"
if [[ -n "$CURRENT_LOCALHOST" ]]; then
  echo "Current macOS LocalHostName: ${CURRENT_LOCALHOST}.local"
else
  echo "No macOS LocalHostName is currently set."
fi

echo "The app QR code will prefer the Mac's Bonjour hostname, e.g. http://${DEFAULT_LOCALHOST}.local:8080"
read -r -p "Set this Mac's local hostname to ${DEFAULT_LOCALHOST}.local now? Requires sudo. [y/N] " host_answer
case "${host_answer:-}" in
  y|Y|yes|YES)
    sudo scutil --set ComputerName "Church Cap"
    sudo scutil --set LocalHostName "$DEFAULT_LOCALHOST"
    sudo scutil --set HostName "${DEFAULT_LOCALHOST}.local"
    echo "Hostname set. On the same network, try: http://${DEFAULT_LOCALHOST}.local:8080"
    ;;
  *)
    echo "Hostname not changed. The app will use the current Bonjour hostname if available, otherwise it will fall back to the LAN IP."
    ;;
esac

step "7/8 Installing Base translation dependencies/models"
echo "Base translation uses Argos Translate for local, offline text translation after language packs are downloaded."
echo "This is experimental. It increases setup time, disk usage, CPU/RAM use during services, and translations may be inaccurate."
echo "The installer will use .venv only, then download common English -> target language packs where Argos provides them."
echo "You can install all Base packs later from the operator Languages page, or install the heavier Core SMaLL-100 model when needed."
echo "Live translated captions will remain OFF in the operator web page until the operator enables them."
echo ""
echo "Translation resource options:"
echo "  1) Install common Base packs (recommended)"
echo "  2) Install all available Base packs"
echo "  3) Install common Base packs and optional Core model"
echo "  4) Skip translation resources for now"
read -r -p "Choose translation setup [1]: " translation_answer
case "${translation_answer:-1}" in
  2)
    ./scripts/install-translation-models-argos.sh --all || echo "Argos model installation did not complete. You can rerun ./scripts/install-translation-models-argos.sh --all later."
    ;;
  3)
    ./scripts/install-translation-models-argos.sh || echo "Argos model installation did not complete. You can rerun ./scripts/install-translation-models-argos.sh later."
    ./scripts/install-small100-core.sh || echo "Core model installation did not complete. You can rerun ./scripts/install-small100-core.sh later."
    ;;
  4)
    echo "Skipping translation resources. You can install them later from the operator Languages page."
    ;;
  *)
    ./scripts/install-translation-models-argos.sh || echo "Argos model installation did not complete. You can rerun ./scripts/install-translation-models-argos.sh later."
    ;;
esac

step "8/8 Optional local HTTPS tooling"
echo "Local HTTPS without warnings on visitors' phones is not automatic. Browsers only trust certificates from a trusted CA."
echo "mkcert is useful for trusted testing on this Mac, but each phone would need the local CA installed to avoid warnings."
read -r -p "Install mkcert for local HTTPS testing on this Mac? [y/N] " mkcert_answer
case "${mkcert_answer:-}" in
  y|Y|yes|YES)
    brew list mkcert >/dev/null 2>&1 || brew install mkcert
    brew list nss >/dev/null 2>&1 || brew install nss || true
    mkcert -install
    ./scripts/generate-trusted-local-cert-macos.sh || true
    ;;
  *)
    echo "Skipping mkcert. You can still use HTTP locally or generate a self-signed cert later."
    ;;
esac

cat <<'DONE'

Setup complete.

Start the server:
  ./start-macos.sh

After first setup, do not recreate .venv or copy .env.example over .env each time.
Use ./start-macos.sh for normal Sunday use.

Open the operator page:
  http://localhost:9090/operator

On first run, create the operator password in the web page.
For church use, connect this Mac by Ethernet and use a USB audio interface from the sound desk.

DONE
