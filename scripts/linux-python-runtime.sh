#!/usr/bin/env bash
# Verified, project-local Python bootstrap for Linux distributions whose system
# Python is newer than Church Cap v0.9.0's pinned ML packages support.

CHURCH_CAP_UV_VERSION="0.12.3"
CHURCH_CAP_MANAGED_PYTHON_VERSION="3.12"

linux_uv_target() {
  local architecture=""
  local libc="gnu"

  case "$(uname -m)" in
    x86_64|amd64) architecture="x86_64" ;;
    aarch64|arm64) architecture="aarch64" ;;
    *)
      echo "Church Cap's automatic Python installer supports x86_64 and ARM64 Linux computers." >&2
      echo "Detected architecture: $(uname -m)" >&2
      return 1
      ;;
  esac

  if ldd --version 2>&1 | grep -qi musl || compgen -G '/lib/ld-musl-*.so.1' >/dev/null; then
    libc="musl"
  fi
  printf '%s-unknown-linux-%s\n' "$architecture" "$libc"
}

linux_uv_sha256() {
  case "$1" in
    x86_64-unknown-linux-gnu) printf '%s\n' '600cf9a742aca00d292673b16b5acffaa7b8c269a364ad0c2e79498dcb1fe101' ;;
    aarch64-unknown-linux-gnu) printf '%s\n' 'bb66cb52e7b1823aed1183630d8d8e5c958840d584a4c55ec10a4cfc168dcca2' ;;
    x86_64-unknown-linux-musl) printf '%s\n' '0643b9fb8c9fb27458e709ce6ff939695013c41975ff7b02d3f3b138d8d4bdb3' ;;
    aarch64-unknown-linux-musl) printf '%s\n' 'fa513fca1eb2913334c944fe9adbdd410274a1cbe8dd05d03699a9eb85311d4e' ;;
    *) return 1 ;;
  esac
}

linux_sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print tolower($1)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print tolower($1)}'
  else
    echo "A SHA-256 utility is required (sha256sum or shasum)." >&2
    return 1
  fi
}

install_managed_linux_python() {
  local app_dir="$1"
  local install_tmp="$2"
  local target=""
  local expected_sha256=""
  local actual_sha256=""
  local archive=""
  local extract_dir=""
  local archive_member=""
  local uv_dir="$app_dir/.tools/uv"
  local uv_bin="$uv_dir/uv"
  local managed_python=""

  target="$(linux_uv_target)" || return 1
  expected_sha256="$(linux_uv_sha256 "$target")" || return 1
  archive="$install_tmp/uv-${CHURCH_CAP_UV_VERSION}-${target}.tar.gz"
  extract_dir="$install_tmp/uv-${CHURCH_CAP_UV_VERSION}-${target}"
  archive_member="uv-${target}/uv"

  mkdir -p "$install_tmp" "$uv_dir"
  if [[ ! -x "$uv_bin" ]] || [[ "$($uv_bin --version 2>/dev/null || true)" != "uv ${CHURCH_CAP_UV_VERSION}"* ]]; then
    echo "No compatible system Python was found." >&2
    echo "Downloading verified uv ${CHURCH_CAP_UV_VERSION} for ${target}..." >&2
    curl -L --fail --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 300 \
      -o "$archive" \
      "https://releases.astral.sh/github/uv/releases/download/${CHURCH_CAP_UV_VERSION}/uv-${target}.tar.gz"
    actual_sha256="$(linux_sha256_file "$archive")" || return 1
    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
      echo "The downloaded Python installer failed SHA-256 verification." >&2
      echo "Expected: $expected_sha256" >&2
      echo "Received: $actual_sha256" >&2
      return 1
    fi
    local archive_listing=""
    archive_listing="$(tar -tzf "$archive")" || return 1
    if ! grep -Fx "$archive_member" <<<"$archive_listing" >/dev/null; then
      echo "The verified uv archive did not contain the expected executable." >&2
      return 1
    fi
    if grep -E '(^/|(^|/)\.\.(/|$))' <<<"$archive_listing" >/dev/null; then
      echo "The verified uv archive contained an unsafe path." >&2
      return 1
    fi
    rm -rf -- "$extract_dir"
    mkdir -p "$extract_dir"
    tar -xzf "$archive" -C "$extract_dir" "$archive_member"
    cp "$extract_dir/$archive_member" "$uv_bin"
    chmod 0755 "$uv_bin"
  fi

  export UV_PYTHON_INSTALL_DIR="$app_dir/.tools/python"
  export UV_PYTHON_BIN_DIR="$app_dir/.tools/python-bin"
  export UV_CACHE_DIR="$install_tmp/uv-cache"
  export UV_NO_PROGRESS=1
  export UV_MANAGED_PYTHON=1

  echo "Installing project-local Python ${CHURCH_CAP_MANAGED_PYTHON_VERSION}..." >&2
  "$uv_bin" python install "$CHURCH_CAP_MANAGED_PYTHON_VERSION" --managed-python --no-progress >&2
  managed_python="$($uv_bin python find "$CHURCH_CAP_MANAGED_PYTHON_VERSION" --managed-python)"
  if [[ ! -x "$managed_python" ]] || ! python_is_supported "$managed_python"; then
    echo "The downloaded Python runtime could not be validated." >&2
    return 1
  fi
  printf '%s\n' "$managed_python"
}
