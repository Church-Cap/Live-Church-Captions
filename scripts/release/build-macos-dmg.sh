#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_ROOT/scripts/release/macos-signing-identity.sh"
APP_PATH="${CHURCH_CAP_MACOS_APP:-$PROJECT_ROOT/dist/macos-arm64/Church Cap.app}"
VERSION="${CHURCH_CAP_RELEASE_VERSION:-0.9.0}"
OUTPUT_PATH="${CHURCH_CAP_MACOS_DMG:-$PROJECT_ROOT/dist/Church-Cap-v$VERSION-macOS-Apple-Silicon.dmg}"
IDENTITY="${CHURCH_CAP_CODESIGN_IDENTITY:-}"
IDENTITY_SHA1="${CHURCH_CAP_CODESIGN_IDENTITY_SHA1:-}"

fail() {
  echo "error: $*" >&2
  exit 1
}

if [[ "$(basename "$OUTPUT_PATH")" == *-internal.dmg ]]; then
  fail "the production DMG output must not use the internal artifact name"
fi
if [[ ! -d "$APP_PATH" || ! -f "$APP_PATH/Contents/Info.plist" ]]; then
  fail "signed and notarized Church Cap application not found: $APP_PATH"
fi
church_cap_resolve_developer_id "$IDENTITY" "$IDENTITY_SHA1" || exit 1

APP_VERSION="$(plutil -extract CFBundleShortVersionString raw -o - "$APP_PATH/Contents/Info.plist")"
if [[ "$APP_VERSION" != "$VERSION" ]]; then
  fail "application version $APP_VERSION does not match requested DMG version $VERSION"
fi

"$PROJECT_ROOT/scripts/release/check-macos-app-bundle.sh" "$APP_PATH"
SIGNING_DETAILS="$(codesign -d --verbose=4 "$APP_PATH" 2>&1)"
if [[ "$SIGNING_DETAILS" != *"Authority=$IDENTITY"* ]]; then
  fail "the production DMG must contain an app signed by the requested Developer ID identity"
fi
if [[ "$SIGNING_DETAILS" == *"TeamIdentifier=not set"* || "$SIGNING_DETAILS" != *"TeamIdentifier="* ]]; then
  fail "the production DMG application has no Apple Team ID"
fi
xcrun stapler validate "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH"

CHURCH_CAP_MACOS_APP="$APP_PATH" \
CHURCH_CAP_MACOS_DMG="$OUTPUT_PATH" \
CHURCH_CAP_MACOS_DMG_KIND="public" \
  "$PROJECT_ROOT/scripts/release/build-internal-macos-dmg.sh"

echo "Production Apple Silicon DMG created from the notarized app: $OUTPUT_PATH"
echo "Run notarize-macos-dmg.sh before publishing this artifact."
