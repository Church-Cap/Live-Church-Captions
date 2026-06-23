#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This setup script is intended for Linux." >&2
  exit 1
fi

# shellcheck source=scripts/linux-system-packages.sh
source "$APP_DIR/scripts/linux-system-packages.sh"

repair_script_permissions() {
  chmod +x ./*.sh scripts/*.sh scripts/*.py 2>/dev/null || true
}

create_env_if_missing() {
  if [[ -f ".env" ]]; then
    echo ".env already exists; keeping your current settings."
  elif [[ -f ".env.example" ]]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  elif [[ -f "env.example" ]]; then
    cp env.example .env
    echo "Created .env from env.example"
  else
    echo "Could not find .env.example or env.example. Re-download Church Cap and try again." >&2
    exit 1
  fi
}

step() {
  echo ""
  echo "==> $1"
}

repair_script_permissions
DISTRO="$(linux_distro_label)"
PACKAGE_MANAGER="$(linux_package_manager || true)"

cat <<INTRO

=====================================================
 Church Cap first-time setup for Linux
=====================================================

Detected: $DISTRO
Package manager: ${PACKAGE_MANAGER:-not detected}

This installer supports the common package-manager families:
  apt (Ubuntu, Debian and derivatives)
  dnf/yum (AlmaLinux, Rocky Linux, RHEL, Fedora and derivatives)
  zypper (openSUSE)
  pacman (Arch Linux and derivatives)
  apk (Alpine Linux)

It installs only the system packages needed for Python, PortAudio and builds.
Church Cap's Python packages stay inside this folder's .venv.
It does not enable extra repositories or install NVIDIA drivers/CUDA.

INTRO

if [[ -z "$PACKAGE_MANAGER" ]]; then
  echo "No supported package manager was found." >&2
  echo "Install Python 3.10+, venv, pip, compiler/build tools, PortAudio development headers, libsndfile, curl, and unzip; then rerun setup." >&2
  exit 1
fi

read -r -p "Continue and install/check system packages? [y/N] " answer
case "${answer:-}" in
  y|Y|yes|YES) ;;
  *) echo "Setup cancelled."; exit 0 ;;
esac

step "1/5 Installing required system packages"
install_linux_system_packages "$PACKAGE_MANAGER"

step "2/5 Finding Python 3.10 or newer"
PYTHON_BIN="$(find_supported_linux_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "A supported Python was not found after package installation." >&2
  echo "AlmaLinux/RHEL-family users should enable the normal AppStream repositories and install Python 3.11 or newer." >&2
  exit 1
fi
echo "Using $("$PYTHON_BIN" --version) at $PYTHON_BIN"

step "3/5 Creating the local virtual environment"
if [[ ! -d ".venv" ]]; then
  "$PYTHON_BIN" -m venv .venv
else
  echo ".venv already exists; reusing it."
fi
VENV_PY="$APP_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "The virtual environment was not created correctly." >&2
  exit 1
fi

step "4/5 Installing Church Cap inside .venv"
"$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$VENV_PY" -m pip install --upgrade pip "setuptools<82" wheel
"$VENV_PY" -m pip install -r requirements.txt
mkdir -p data logs certs
create_env_if_missing

step "5/5 Optional local translation resources"
echo "Translation is optional and experimental. You can install it later from the operator Languages page."
echo "  1) Install common Base / Argos packs"
echo "  2) Install all available Base / Argos packs"
echo "  3) Install common Base packs and optional Core / SMaLL-100"
echo "  4) Skip translation resources"
read -r -p "Choose translation setup [4]: " translation_answer
case "${translation_answer:-4}" in
  1) ./scripts/install-translation-models-argos.sh ;;
  2) ./scripts/install-translation-models-argos.sh --all ;;
  3)
    ./scripts/install-translation-models-argos.sh
    ./scripts/install-small100-core.sh
    ;;
  *) echo "Skipping translation resources." ;;
esac

cat <<'DONE'

Setup complete.

Start Church Cap:
  ./start-linux.sh

Operator page:
  http://localhost:9090/operator

Audience phones use the LAN/IP QR code shown on the operator page.
For a dedicated Linux caption server, run Church Cap as a normal user rather than root.

DONE
