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
# shellcheck source=scripts/linux-python-runtime.sh
source "$APP_DIR/scripts/linux-python-runtime.sh"

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

It installs only the system packages needed for audio and Python packages.
Church Cap's Python packages stay inside this folder's .venv. If the Linux
distribution only provides Python 3.14 or newer, setup downloads a SHA-256
verified Python 3.12 runtime and keeps it inside this folder's .tools directory.
It does not enable extra repositories or install NVIDIA drivers. If an NVIDIA
driver is already working, setup can optionally add the CUDA 12 cuBLAS and
cuDNN 9 runtime libraries required by CTranslate2 inside the local .venv.
If an active Linux firewall is detected, setup can also add the recommended
audience-only TCP rule after asking for permission.

INTRO

if [[ -z "$PACKAGE_MANAGER" ]]; then
  echo "No supported package manager was found." >&2
  echo "Install compiler/build tools, PortAudio development headers, libsndfile, curl, tar, and CA certificates; then rerun setup." >&2
  exit 1
fi

read -r -p "Continue and install/check system packages? [y/N] " answer
case "${answer:-}" in
  y|Y|yes|YES) ;;
  *) echo "Setup cancelled."; exit 0 ;;
esac

step "1/7 Installing required system packages"
install_linux_system_packages "$PACKAGE_MANAGER"

step "2/7 Preparing a compatible Python (3.10 through 3.13)"
INSTALL_TMP="$APP_DIR/.install-tmp"
mkdir -p "$INSTALL_TMP"
cleanup_install_tmp() {
  rm -rf -- "$INSTALL_TMP"
}
trap cleanup_install_tmp EXIT
VENV_INCOMPLETE_MARKER="$APP_DIR/.venv/.church-cap-install-incomplete"
if [[ -d ".venv" ]] && {
  [[ ! -x ".venv/bin/python" ]] ||
  ! python_is_supported ".venv/bin/python" ||
  [[ -f "$VENV_INCOMPLETE_MARKER" ]]
}; then
  echo "The existing Church Cap .venv is incomplete or uses an unsupported Python." >&2
  [[ ! -x ".venv/bin/python" ]] || echo "Existing environment: $(.venv/bin/python --version 2>&1)" >&2
  echo "It may be consuming the disk quota needed by a clean installation." >&2
  read -r -p "Remove only this Church Cap .venv and recreate it? [y/N] " replace_venv
  case "${replace_venv:-no}" in
    y|Y|yes|YES) rm -rf -- "$APP_DIR/.venv" ;;
    *) echo "Setup stopped without changing the existing .venv."; exit 1 ;;
  esac
fi
require_linux_install_space "$APP_DIR" $((8 * 1024 * 1024))
PYTHON_BIN="$(find_supported_linux_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "The system Python is not compatible with Church Cap v0.9.0's pinned ML packages." >&2
  echo "Preparing a verified, project-local Python 3.12 without changing the system Python..." >&2
  if ! PYTHON_BIN="$(install_managed_linux_python "$APP_DIR" "$INSTALL_TMP")"; then
    echo "Church Cap could not prepare its project-local Python 3.12 runtime." >&2
    echo "Check the internet connection and available storage, then rerun bash setup-linux.sh." >&2
    exit 1
  fi
fi
echo "Using $("$PYTHON_BIN" --version) at $PYTHON_BIN"

step "3/7 Creating the local virtual environment"
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

step "4/7 Installing Church Cap inside .venv"
export TMPDIR="$INSTALL_TMP"
export PIP_NO_CACHE_DIR=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
touch "$VENV_INCOMPLETE_MARKER"
"$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
if ! "$VENV_PY" -m pip install --no-cache-dir --upgrade "pip==26.1.2" "setuptools<82" wheel ||
   ! "$VENV_PY" -m pip install --no-cache-dir -r requirements.txt; then
  echo "" >&2
  echo "Church Cap's Python dependencies could not be installed." >&2
  linux_storage_diagnostics "$APP_DIR" >&2
  echo "If the error says 'Disk quota exceeded', free space from this user account or ask the administrator to raise its quota." >&2
  echo "A failed attempt may have left a partial .venv; rerun setup and approve removing only that Church Cap .venv." >&2
  exit 1
fi
rm -f -- "$VENV_INCOMPLETE_MARKER"
mkdir -p data logs certs
create_env_if_missing

VIEWER_PORT="$("$VENV_PY" -c 'from app.settings import get_settings; print(get_settings().viewer_port)' 2>/dev/null || true)"
if [[ ! "$VIEWER_PORT" =~ ^[0-9]+$ ]] || (( VIEWER_PORT < 1 || VIEWER_PORT > 65535 )); then
  VIEWER_PORT=8080
fi
AUDIENCE_IP="$("$VENV_PY" -c 'from app.networking import local_ip; print(local_ip())' 2>/dev/null || true)"
AUDIENCE_IP="${AUDIENCE_IP:-127.0.0.1}"

step "5/7 Checking recommended audience firewall access"
FIREWALL_MANAGER="$(linux_active_firewall_manager || true)"
FIREWALL_ZONE=""
FIREWALL_RULE_READY="no"
if [[ "$FIREWALL_MANAGER" == "firewalld" ]]; then
  FIREWALL_ZONE="$(linux_firewalld_zone || true)"
  if [[ -n "$FIREWALL_ZONE" ]] && linux_firewalld_port_is_allowed "$VIEWER_PORT" "$FIREWALL_ZONE"; then
    FIREWALL_RULE_READY="yes"
  fi
fi

if [[ "$FIREWALL_RULE_READY" == "yes" ]]; then
  echo "Audience TCP port $VIEWER_PORT is already allowed by firewalld in zone $FIREWALL_ZONE."
elif [[ -n "$FIREWALL_MANAGER" ]]; then
  echo "Recommended: allow audience phones to reach Church Cap on TCP port $VIEWER_PORT."
  if [[ "$FIREWALL_MANAGER" == "firewalld" ]]; then
    echo "Detected firewalld zone: ${FIREWALL_ZONE:-unknown}."
  else
    echo "Detected active firewall: UFW."
  fi
  echo "This opens only the public caption viewer port. It does not open operator port 9090."
  echo "Use this only on a trusted church/AV network; router guest isolation may still need a separate rule."
  read -r -p "Add the recommended audience firewall rule now? [y/N] " firewall_answer
  case "${firewall_answer:-no}" in
    y|Y|yes|YES)
      if [[ "$FIREWALL_MANAGER" == "firewalld" && -z "$FIREWALL_ZONE" ]]; then
        echo "Could not determine the active firewalld zone; no rule was changed." >&2
      elif allow_linux_audience_port "$FIREWALL_MANAGER" "$VIEWER_PORT" "$FIREWALL_ZONE"; then
        echo "Allowed TCP port $VIEWER_PORT for audience captions."
      else
        echo "The firewall rule could not be added. Setup will continue." >&2
        echo "Allow TCP port $VIEWER_PORT manually before audience phones connect." >&2
      fi
      ;;
    *)
      echo "Skipping the firewall change. Audience QR codes may not work until TCP port $VIEWER_PORT is allowed."
      ;;
  esac
else
  echo "No active supported firewalld or UFW firewall was detected; setup did not change the host firewall."
  echo "If phones still cannot connect, check guest Wi-Fi/client isolation on the router."
fi

step "6/7 Checking optional NVIDIA CUDA runtime"
# shellcheck source=scripts/linux-cuda-runtime.sh
source "$APP_DIR/scripts/linux-cuda-runtime.sh"
prepare_linux_python_cuda_library_path "$VENV_PY"
read -r NVIDIA_GPU_VISIBLE CUDA_RUNTIME_READY < <(
  "$VENV_PY" -c 'from app.hardware import detect_hardware_acceleration; status = detect_hardware_acceleration(); print("yes" if status.nvidia_smi_available or status.cuda_device_count > 0 else "no", "yes" if status.cuda_available else "no")'
)
if [[ "$NVIDIA_GPU_VISIBLE" == "yes" ]]; then
  if [[ "$CUDA_RUNTIME_READY" == "yes" ]]; then
    echo "NVIDIA CUDA 12 runtime is already ready for CTranslate2."
    "$VENV_PY" scripts/check-gpu.py
  else
    echo "An NVIDIA driver/GPU is visible, but CTranslate2 cannot yet load all required CUDA runtime libraries."
    echo "Church Cap needs CUDA 12 cuBLAS and cuDNN 9; nvidia-smi alone does not install these libraries."
    echo "The optional runtime is a large internet download and stays inside this Church Cap folder."
    read -r -p "Install the local CUDA runtime libraries inside .venv now? [y/N] " cuda_answer
    case "${cuda_answer:-no}" in
      y|Y|yes|YES) ./install-cuda-runtime-linux.sh ;;
      *)
        echo "Skipping local CUDA runtime. Church Cap will use CPU / int8 unless a compatible system runtime is available."
        echo "You can install it later with: ./install-cuda-runtime-linux.sh"
        ;;
    esac
  fi
else
  echo "No working NVIDIA driver/GPU was detected; skipping the optional CUDA runtime."
  echo "Church Cap will use CPU / int8."
fi

step "7/7 Preparing browser-guided language setup"
echo "No optional translation model is downloaded by this terminal setup."
echo "The first-run browser assistant offers friendly language packs,"
echo "recommends a safe pack and simultaneous-language limit using local hardware checks,"
echo "and can install the selected open-source local translation runtime."
echo "Additional Base and compatibility controls remain available later from Operator > Languages."

cat <<DONE

Setup complete.

Start Church Cap:
  ./start-linux.sh

Operator page:
  http://localhost:9090/operator

Audience phones use the LAN/IP QR code shown on the operator page.
On Linux, the direct-IP QR is the reliable default unless local DNS or mDNS has been configured.
Current audience URL: http://${AUDIENCE_IP}:${VIEWER_PORT}/
If a phone cannot open it, confirm the phone is on the same LAN and that the router does not isolate Wi-Fi clients.
For a dedicated Linux caption server, run Church Cap as a normal user rather than root.

DONE
