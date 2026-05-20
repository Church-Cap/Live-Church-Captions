#!/usr/bin/env bash
set -euo pipefail

REPO_ZIP_URL="https://github.com/Church-Cap/Live-Church-Captions/archive/refs/heads/main.zip"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$APP_DIR")"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET_DIR="$PARENT_DIR/church_cap_update_$STAMP"
TMP_DIR="$(mktemp -d)"
ZIP_PATH="$TMP_DIR/church-cap-main.zip"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Church Cap updater"
echo "This downloads the latest GitHub source into a new folder."
echo "Current folder will not be overwritten:"
echo "  $APP_DIR"
echo ""

read -r -p "Download latest Church Cap from GitHub now? [y/N] " answer
case "${answer:-}" in
  y|Y|yes|YES) ;;
  *) echo "Update cancelled."; exit 0 ;;
esac

echo "Downloading:"
echo "  $REPO_ZIP_URL"
curl -L --fail -o "$ZIP_PATH" "$REPO_ZIP_URL"

mkdir -p "$TARGET_DIR"
unzip -q "$ZIP_PATH" -d "$TMP_DIR"
EXTRACTED_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'Live-Church-Captions-*' | head -n 1)"
if [[ -z "$EXTRACTED_DIR" ]]; then
  echo "Could not find extracted GitHub folder." >&2
  exit 1
fi

cp -R "$EXTRACTED_DIR"/. "$TARGET_DIR"/

if [[ -f "$APP_DIR/.env" && ! -f "$TARGET_DIR/.env" ]]; then
  cp "$APP_DIR/.env" "$TARGET_DIR/.env"
fi

for file in config/glossary.csv config/profanity_filter.txt; do
  if [[ -f "$APP_DIR/$file" ]]; then
    mkdir -p "$TARGET_DIR/$(dirname "$file")"
    cp "$APP_DIR/$file" "$TARGET_DIR/$file"
  fi
done

chmod +x "$TARGET_DIR"/*.sh "$TARGET_DIR"/scripts/*.sh "$TARGET_DIR"/scripts/*.py 2>/dev/null || true

echo ""
echo "Update downloaded to:"
echo "  $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  cd \"$TARGET_DIR\""
echo "  bash setup-macos.sh"
echo "  ./start-macos.sh"
