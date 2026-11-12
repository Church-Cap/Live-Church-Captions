#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_ROOT/scripts/release/macos-signing-identity.sh"
DMG_PATH="${1:-$PROJECT_ROOT/dist/Church-Cap-v0.9.0-macOS-Apple-Silicon.dmg}"
IDENTITY="${CHURCH_CAP_CODESIGN_IDENTITY:-}"
IDENTITY_SHA1="${CHURCH_CAP_CODESIGN_IDENTITY_SHA1:-}"
NOTARY_PROFILE="${CHURCH_CAP_NOTARY_PROFILE:-}"
LOG_DIR="${CHURCH_CAP_NOTARY_LOG_DIR:-$PROJECT_ROOT/dist/notarization}"

fail() {
  echo "error: $*" >&2
  exit 1
}

if [[ ! -f "$DMG_PATH" ]]; then
  fail "macOS DMG not found: $DMG_PATH"
fi
if [[ "$(basename "$DMG_PATH")" == *-internal.dmg ]]; then
  fail "refusing to notarize an internal/ad-hoc DMG"
fi
church_cap_resolve_developer_id "$IDENTITY" "$IDENTITY_SHA1" || exit 1
SIGNING_IDENTITY="$CHURCH_CAP_RESOLVED_CODESIGN_IDENTITY"
if [[ -z "$NOTARY_PROFILE" ]]; then
  fail "set CHURCH_CAP_NOTARY_PROFILE to a notarytool keychain profile"
fi

# Validate the saved credentials before changing the DMG. This also catches an
# expired app-specific password or an incorrect Team ID early.
xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null

codesign --force --sign "$SIGNING_IDENTITY" --timestamp "$DMG_PATH"
codesign --verify --strict --verbose=2 "$DMG_PATH"

mkdir -p "$LOG_DIR"
RESULT_JSON="$(mktemp "${TMPDIR:-/private/tmp}/church-cap-notary.XXXXXX.json")"
trap 'rm -f "$RESULT_JSON"' EXIT

xcrun notarytool submit "$DMG_PATH" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait \
  --output-format json >"$RESULT_JSON"

SUBMISSION_ID="$(plutil -extract id raw -o - "$RESULT_JSON")"
STATUS="$(plutil -extract status raw -o - "$RESULT_JSON")"
cp "$RESULT_JSON" "$LOG_DIR/$SUBMISSION_ID-submission.json"
xcrun notarytool log "$SUBMISSION_ID" \
  --keychain-profile "$NOTARY_PROFILE" \
  "$LOG_DIR/$SUBMISSION_ID-log.json"

if [[ "$STATUS" != "Accepted" ]]; then
  fail "Apple notarization status was $STATUS; inspect $LOG_DIR/$SUBMISSION_ID-log.json"
fi

xcrun stapler staple "$DMG_PATH"
xcrun stapler validate "$DMG_PATH"
spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG_PATH"

echo "Developer ID signing, notarization, stapling, and Gatekeeper assessment passed: $DMG_PATH"
echo "Notarization evidence: $LOG_DIR/$SUBMISSION_ID-log.json"
