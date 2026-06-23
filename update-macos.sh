#!/usr/bin/env bash
set -Eeuo pipefail

LATEST_RELEASE_URL="https://api.github.com/repos/Church-Cap/Live-Church-Captions/releases/latest"
REPO_TAG_ZIP_BASE_URL="https://github.com/Church-Cap/Live-Church-Captions/archive/refs/tags"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
START_SCRIPT="${CHURCH_CAP_UPDATE_START_SCRIPT:-start-macos.sh}"
SETUP_SCRIPT="${CHURCH_CAP_UPDATE_SETUP_SCRIPT:-setup-macos.sh}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TMP_DIR="$(mktemp -d)"
ZIP_PATH="$TMP_DIR/church-cap-release.zip"
PRESERVE_DIR="$TMP_DIR/preserve"
STAGE_DIR="$TMP_DIR/staged-release"
MANIFEST_PATH="$TMP_DIR/staged-release.sha256"
BACKUP_ROOT="$APP_DIR/data/update-backups"
BACKUP_DIR="$BACKUP_ROOT/pre-update-$STAMP"
YES=0
CHECK_ONLY=0
RESTART=0
SERVER_PID=""
REPLACEMENT_STARTED=0
UPDATE_COMPLETE=0

cleanup() {
  rm -rf "$TMP_DIR"
}

on_error() {
  local line="${1:-unknown}"
  if [[ "$REPLACEMENT_STARTED" -eq 1 && "$UPDATE_COMPLETE" -ne 1 ]]; then
    echo ""
    echo "Update failed around line $line. Restoring the previous Church Cap files..."
    restore_backup || echo "Automatic rollback did not complete. Backup remains at: $BACKUP_DIR" >&2
  fi
}

trap 'on_error $LINENO' ERR
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1; shift ;;
    --check) CHECK_ONLY=1; shift ;;
    --restart) RESTART=1; shift ;;
    --server-pid)
      SERVER_PID="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

read_local_version() {
  sed -n 's/.*app_version: str = "\([^"]*\)".*/\1/p' "$APP_DIR/app/settings.py" | head -n 1 | sed 's/^v\.//;s/^v//'
}

normalise_version() {
  printf '%s' "${1:-}" | sed 's/^v\.//;s/^v//'
}

fetch_remote_tag() {
  curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 45 \
    -H "Accept: application/vnd.github+json" \
    -H "User-Agent: Church-Cap-Updater" \
    "$LATEST_RELEASE_URL" |
    python3 -c 'import json, sys; print(str(json.load(sys.stdin).get("tag_name") or "").strip())'
}

version_newer() {
  python3 - "$1" "$2" <<'PY'
import re
import sys

def parts(value):
    return tuple(int(x) for x in re.findall(r"\d+", value or "0"))

sys.exit(0 if parts(sys.argv[1]) > parts(sys.argv[2]) else 1)
PY
}

version_from_settings_file() {
  local settings_file="$1"
  sed -n 's/.*app_version: str = "\([^"]*\)".*/\1/p' "$settings_file" | head -n 1 | sed 's/^v\.//;s/^v//'
}

sync_env_key() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  [[ -f "$env_file" && -n "$value" ]] || return 0
  if grep -q "^${key}=" "$env_file"; then
    python3 - "$env_file" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text().splitlines()
updated = []
done = False
for line in lines:
    if line.startswith(f"{key}="):
        updated.append(f"{key}={value}")
        done = True
    else:
        updated.append(line)
if not done:
    updated.append(f"{key}={value}")
path.write_text("\n".join(updated) + "\n")
PY
  else
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}

copy_preserved_file() {
  local relative_path="$1"
  if [[ -f "$APP_DIR/$relative_path" ]]; then
    mkdir -p "$PRESERVE_DIR/$(dirname "$relative_path")"
    cp "$APP_DIR/$relative_path" "$PRESERVE_DIR/$relative_path"
  fi
}

validate_release_tree() {
  local release_dir="$1"
  local required_files=(
    "app/main.py"
    "app/settings.py"
    "app/updater.py"
    "app/platforms.py"
    "app/service_leader_auth.py"
    "app/templates/service_leader.html"
    "app/templates/service_leader_pair.html"
    "app/templates/service_leader_pairing.html"
    "app/templates/operator.html"
    "app/static/styles.css"
    "requirements.txt"
    "setup-macos.sh"
    "start-macos.sh"
    "update-macos.sh"
    "setup-windows.cmd"
    "update-windows.ps1"
    "setup-linux.sh"
    "start-linux.sh"
    "update-linux.sh"
    "scripts/linux-system-packages.sh"
    "env.example"
  )
  for required in "${required_files[@]}"; do
    if [[ ! -f "$release_dir/$required" ]]; then
      echo "Downloaded release is missing required file: $required" >&2
      return 1
    fi
  done
}

build_manifest() {
  (
    cd "$STAGE_DIR"
    if command -v shasum >/dev/null 2>&1; then
      find . -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$MANIFEST_PATH"
    else
      find . -type f -print0 | sort -z | xargs -0 sha256sum > "$MANIFEST_PATH"
    fi
  )
}

verify_manifest_in_app() {
  (
    cd "$APP_DIR"
    if command -v shasum >/dev/null 2>&1; then
      shasum -a 256 -c "$MANIFEST_PATH" >/dev/null
    else
      sha256sum -c "$MANIFEST_PATH" >/dev/null
    fi
  )
}

backup_current_files() {
  mkdir -p "$BACKUP_DIR"
  if [[ -f "$APP_DIR/.env" ]]; then
    cp "$APP_DIR/.env" "$BACKUP_DIR/.env"
  fi
  shopt -s dotglob nullglob
  for item in "$APP_DIR"/*; do
    local name
    name="$(basename "$item")"
    case "$name" in
      .env|.venv|.git|data|logs|certs) continue ;;
    esac
    cp -R "$item" "$BACKUP_DIR"/
  done
  shopt -u dotglob nullglob
}

remove_replaceable_files() {
  shopt -s dotglob nullglob
  for item in "$APP_DIR"/*; do
    local name
    name="$(basename "$item")"
    case "$name" in
      .env|.venv|.git|data|logs|certs) continue ;;
    esac
    rm -rf "$item"
  done
  shopt -u dotglob nullglob
}

restore_backup() {
  [[ -d "$BACKUP_DIR" ]] || return 1
  remove_replaceable_files
  cp -R "$BACKUP_DIR"/. "$APP_DIR"/
  chmod +x "$APP_DIR"/*.sh "$APP_DIR"/scripts/*.sh "$APP_DIR"/scripts/*.py 2>/dev/null || true
  echo "Previous Church Cap files restored from:"
  echo "  $BACKUP_DIR"
}

CURRENT_VERSION="$(read_local_version)"
REMOTE_TAG="$(fetch_remote_tag)"
REMOTE_VERSION="$(normalise_version "$REMOTE_TAG")"
if [[ -z "$REMOTE_TAG" || -z "$REMOTE_VERSION" ]]; then
  echo "Could not read the latest Church Cap release tag from GitHub." >&2
  exit 1
fi
REPO_ZIP_URL="$REPO_TAG_ZIP_BASE_URL/$REMOTE_TAG.zip"

echo "Church Cap updater"
echo "Current version: v.${CURRENT_VERSION:-unknown}"
echo "Latest GitHub release: $REMOTE_TAG"
echo "  $APP_DIR"
echo ""

if ! version_newer "$REMOTE_VERSION" "$CURRENT_VERSION"; then
  echo "Church Cap is up to date."
  exit 0
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Update available: v.$REMOTE_VERSION"
  exit 0
fi

if [[ "$YES" -ne 1 ]]; then
  read -r -p "Replace this Church Cap folder with v.$REMOTE_VERSION now? [y/N] " answer
  case "${answer:-}" in
    y|Y|yes|YES) ;;
    *) echo "Update cancelled."; exit 0 ;;
  esac
fi

echo "Downloading:"
echo "  $REPO_ZIP_URL"
curl -L --fail --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 240 -o "$ZIP_PATH" "$REPO_ZIP_URL"

echo "Checking downloaded ZIP integrity..."
unzip -tq "$ZIP_PATH" >/dev/null

unzip -q "$ZIP_PATH" -d "$TMP_DIR"
EXTRACTED_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'Live-Church-Captions-*' | head -n 1)"
if [[ -z "$EXTRACTED_DIR" ]]; then
  echo "Could not find extracted GitHub folder." >&2
  exit 1
fi

validate_release_tree "$EXTRACTED_DIR"
EXTRACTED_VERSION="$(version_from_settings_file "$EXTRACTED_DIR/app/settings.py")"
if [[ "$EXTRACTED_VERSION" != "$REMOTE_VERSION" ]]; then
  echo "Downloaded release version v.$EXTRACTED_VERSION did not match GitHub release $REMOTE_TAG." >&2
  exit 1
fi

mkdir -p "$PRESERVE_DIR"
copy_preserved_file ".env"
copy_preserved_file "config/glossary.csv"
copy_preserved_file "config/profanity_filter.txt"

mkdir -p "$STAGE_DIR"
cp -R "$EXTRACTED_DIR"/. "$STAGE_DIR"/
cp -R "$PRESERVE_DIR"/. "$STAGE_DIR"/ 2>/dev/null || true

REMOTE_FEEDBACK_EMAIL="$(sed -n 's/^FEEDBACK_EMAIL=//p' "$STAGE_DIR/env.example" | head -n 1)"
sync_env_key "$STAGE_DIR/.env" "APP_VERSION" "$REMOTE_VERSION"
sync_env_key "$STAGE_DIR/.env" "FEEDBACK_EMAIL" "$REMOTE_FEEDBACK_EMAIL"
chmod +x "$STAGE_DIR"/*.sh "$STAGE_DIR"/scripts/*.sh "$STAGE_DIR"/scripts/*.py 2>/dev/null || true

echo "Checking staged release files..."
build_manifest
COMPILE_PYTHON="python3"
if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  COMPILE_PYTHON="$APP_DIR/.venv/bin/python"
fi
"$COMPILE_PYTHON" -m py_compile "$STAGE_DIR/app/settings.py" "$STAGE_DIR/app/main.py" "$STAGE_DIR/app/updater.py" "$STAGE_DIR/app/platforms.py" "$STAGE_DIR/app/service_leader_auth.py"

if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "Updating Python packages before replacing app files..."
  "$APP_DIR/.venv/bin/python" -m pip install -r "$STAGE_DIR/requirements.txt"
  if [[ -f "$STAGE_DIR/requirements-translation.txt" ]]; then
    "$APP_DIR/.venv/bin/python" -m pip install -r "$STAGE_DIR/requirements-translation.txt"
  fi
else
  echo "No existing .venv found. Run $SETUP_SCRIPT before starting Church Cap."
fi

backup_current_files

if [[ -n "$SERVER_PID" ]]; then
  echo "Stopping running Church Cap process: $SERVER_PID"
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

echo "Replacing Church Cap files in:"
echo "  $APP_DIR"
REPLACEMENT_STARTED=1
remove_replaceable_files
cp -R "$STAGE_DIR"/. "$APP_DIR"/

echo "Verifying installed file checksums..."
verify_manifest_in_app

UPDATE_COMPLETE=1

echo ""
echo "Church Cap updated in place to v.$REMOTE_VERSION."
echo "Rollback backup kept at:"
echo "  $BACKUP_DIR"
echo ""
if [[ "$RESTART" -eq 1 ]]; then
  mkdir -p "$APP_DIR/logs"
  echo "Restarting Church Cap..."
  nohup "$APP_DIR/$START_SCRIPT" > "$APP_DIR/logs/update-restart.log" 2>&1 &
else
  echo "Start Church Cap:"
  echo "  ./$START_SCRIPT"
fi
