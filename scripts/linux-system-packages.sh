#!/usr/bin/env bash
# Shared Linux package detection for setup-linux.sh.
# Keep distro-specific package names here so the main installer stays simple.

linux_package_manager() {
  local manager
  for manager in dnf apt-get zypper pacman apk yum; do
    if command -v "$manager" >/dev/null 2>&1; then
      printf '%s\n' "$manager"
      return 0
    fi
  done
  return 1
}

linux_distro_label() {
  if [[ -r /etc/os-release ]]; then
    (
      . /etc/os-release
      printf '%s\n' "${PRETTY_NAME:-${NAME:-Linux}}"
    )
    return
  fi
  printf 'Linux\n'
}

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Root access is required to install system packages. Install sudo or run setup as root." >&2
    return 1
  fi
}

python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

find_supported_linux_python() {
  local candidate
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_supported "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

dnf_python_package() {
  local package
  for package in python3.12 python3.11 python3; do
    if dnf -q list --available "$package" >/dev/null 2>&1 || rpm -q "$package" >/dev/null 2>&1; then
      printf '%s\n' "$package"
      return 0
    fi
  done
  printf 'python3\n'
}

install_linux_system_packages() {
  local manager="$1"
  local python_package

  case "$manager" in
    apt-get)
      run_as_root apt-get update
      run_as_root apt-get install -y \
        python3 python3-venv python3-pip python3-dev \
        build-essential portaudio19-dev libsndfile1 \
        curl unzip ca-certificates
      ;;
    dnf)
      python_package="$(dnf_python_package)"
      if ! run_as_root dnf install -y \
        "$python_package" "${python_package}-pip" "${python_package}-devel" \
        gcc gcc-c++ make portaudio portaudio-devel libsndfile \
        curl unzip ca-certificates; then
        echo "dnf could not install all required packages." >&2
        echo "On AlmaLinux/Rocky/RHEL, make sure the standard AppStream and CRB repositories are enabled, then rerun setup." >&2
        return 1
      fi
      ;;
    yum)
      run_as_root yum install -y \
        python3 python3-pip python3-devel \
        gcc gcc-c++ make portaudio portaudio-devel libsndfile \
        curl unzip ca-certificates
      ;;
    zypper)
      run_as_root zypper --non-interactive refresh
      run_as_root zypper --non-interactive install \
        python3 python3-pip python3-devel \
        gcc gcc-c++ make portaudio-devel libsndfile1 \
        curl unzip ca-certificates
      ;;
    pacman)
      run_as_root pacman -S --needed --noconfirm \
        python python-pip base-devel portaudio libsndfile \
        curl unzip ca-certificates
      ;;
    apk)
      run_as_root apk add \
        python3 py3-pip py3-virtualenv python3-dev \
        build-base linux-headers portaudio-dev libsndfile-dev \
        curl unzip ca-certificates
      ;;
    *)
      echo "Unsupported package manager: $manager" >&2
      return 1
      ;;
  esac
}
