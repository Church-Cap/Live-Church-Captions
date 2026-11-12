#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${CHURCH_CAP_MACOS_APP:-$PROJECT_ROOT/dist/macos-arm64/Church Cap.app}"
OUTPUT_PATH="${CHURCH_CAP_MACOS_DMG:-$PROJECT_ROOT/dist/Church-Cap-v0.9.0-macOS-Apple-Silicon-internal.dmg}"
DMG_KIND="${CHURCH_CAP_MACOS_DMG_KIND:-internal}"
BACKGROUND_PATH="$PROJECT_ROOT/packaging/macos/dmg/church-cap-dmg-background.png"
BACKGROUND_2X_PATH="$PROJECT_ROOT/packaging/macos/dmg/church-cap-dmg-background@2x.png"
BACKGROUND_TIFF_PATH="$PROJECT_ROOT/packaging/macos/dmg/church-cap-dmg-background.tiff"

if [[ "$DMG_KIND" != "internal" && "$DMG_KIND" != "public" ]]; then
  echo "Unsupported CHURCH_CAP_MACOS_DMG_KIND: $DMG_KIND" >&2
  exit 1
fi
if [[ "$DMG_KIND" == "internal" && "$(basename "$OUTPUT_PATH")" != *-internal.dmg ]]; then
  echo "Internal DMG output must end in -internal.dmg: $OUTPUT_PATH" >&2
  exit 1
fi
if [[ -e "$OUTPUT_PATH" ]]; then
  echo "Refusing to overwrite an existing DMG: $OUTPUT_PATH" >&2
  exit 1
fi

"$PROJECT_ROOT/scripts/release/check-macos-app-bundle.sh" "$APP_PATH"
APP_VERSION="$(plutil -extract CFBundleShortVersionString raw -o - "$APP_PATH/Contents/Info.plist")"
VOLUME_NAME="Church Cap $APP_VERSION"

STAGING_DIR="$(mktemp -d "${TMPDIR:-/private/tmp}/church-cap-dmg.XXXXXX")"
MOUNT_DIR="/Volumes/$VOLUME_NAME"
RW_DMG="$STAGING_DIR/Church-Cap-layout.dmg"
MOUNTED=false
cleanup() {
  if [[ "$MOUNTED" == true ]]; then
    hdiutil detach "$MOUNT_DIR" -quiet || true
  fi
  rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

/usr/bin/xcrun swift "$PROJECT_ROOT/scripts/release/generate-macos-dmg-background.swift" \
  "$PROJECT_ROOT/assets/branding/church-cap-wide-light.png" \
  "$BACKGROUND_PATH" 1
/usr/bin/xcrun swift "$PROJECT_ROOT/scripts/release/generate-macos-dmg-background.swift" \
  "$PROJECT_ROOT/assets/branding/church-cap-wide-light.png" \
  "$BACKGROUND_2X_PATH" 2
tiffutil -cathidpicheck "$BACKGROUND_PATH" "$BACKGROUND_2X_PATH" -out "$BACKGROUND_TIFF_PATH"

CONTENT_DIR="$STAGING_DIR/content"
mkdir -p "$CONTENT_DIR/.background"
ditto "$APP_PATH" "$CONTENT_DIR/Church Cap.app"
# Finder selects the appropriate representation from the multi-resolution
# TIFF produced from the 1x and 2x 72-DPI sources above.
ditto "$BACKGROUND_TIFF_PATH" "$CONTENT_DIR/.background/church-cap-dmg-background.tiff"
ln -s /Applications "$CONTENT_DIR/Applications"

if mount | grep -Fq "on $MOUNT_DIR "; then
  echo "A Church Cap installer volume is already mounted at: $MOUNT_DIR" >&2
  exit 1
fi

hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$CONTENT_DIR" \
  -format UDRW \
  "$RW_DMG"

hdiutil attach "$RW_DMG" \
  -readwrite \
  -noverify \
  -noautoopen \
  -mountpoint "$MOUNT_DIR" >/dev/null
MOUNTED=true

osascript - "$VOLUME_NAME" <<'APPLESCRIPT'
on run argv
  set volumeName to item 1 of argv
  tell application "Finder"
    tell disk volumeName
      open
      set current view of container window to icon view
      set toolbar visible of container window to false
      set statusbar visible of container window to false
      set pathbar visible of container window to false
      set bounds of container window to {120, 120, 780, 610}
      set viewOptions to icon view options of container window
      set arrangement of viewOptions to not arranged
      set icon size of viewOptions to 112
      set text size of viewOptions to 13
      set background picture of viewOptions to file ".background:church-cap-dmg-background.tiff"
      set position of item "Church Cap.app" of container window to {165, 245}
      set position of item "Applications" of container window to {495, 245}
      close
      open
      update without registering applications
      delay 2
    end tell
  end tell
end run
APPLESCRIPT

if [[ ! -f "$MOUNT_DIR/.DS_Store" ]]; then
  echo "Finder did not save the branded DMG layout." >&2
  exit 1
fi

sync
hdiutil detach "$MOUNT_DIR" -quiet
MOUNTED=false

hdiutil convert "$RW_DMG" \
  -format UDZO \
  -imagekey zlib-level=9 \
  -o "$OUTPUT_PATH" >/dev/null

hdiutil verify "$OUTPUT_PATH"
if [[ "$DMG_KIND" == "public" ]]; then
  echo "Apple Silicon DMG layout created at: $OUTPUT_PATH"
else
  echo "Internal Apple Silicon DMG created at: $OUTPUT_PATH"
  echo "This locally sealed image is for internal testing only; Developer ID signing and notarization remain required."
fi
