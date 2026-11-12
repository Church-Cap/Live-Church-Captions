#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$PROJECT_ROOT/dist/macos-arm64/Church Cap.app}"
INFO_PLIST="$APP_PATH/Contents/Info.plist"
SUPERVISOR="$APP_PATH/Contents/MacOS/church-cap-desktop"
ENGINE="$APP_PATH/Contents/Resources/engine/church-cap-engine/church-cap-engine"
PYTHON_FRAMEWORK="$APP_PATH/Contents/Resources/engine/church-cap-engine/_internal/Python.framework"
SOURCE_STYLES="$PROJECT_ROOT/app/static/styles.css"
BUNDLED_STYLES="$APP_PATH/Contents/Resources/engine/church-cap-engine/_internal/app/static/styles.css"

if [[ ! -d "$APP_PATH" || ! -f "$INFO_PLIST" ]]; then
  echo "Church Cap application bundle not found: $APP_PATH" >&2
  exit 1
fi

for executable in "$SUPERVISOR" "$ENGINE"; do
  if [[ ! -x "$executable" ]]; then
    echo "Required application executable is missing: $executable" >&2
    exit 1
  fi
  architectures="$(lipo -archs "$executable")"
  if [[ "$architectures" != "arm64" ]]; then
    echo "Expected an Apple Silicon-only executable: $executable ($architectures)" >&2
    exit 1
  fi
done

read_plist() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$INFO_PLIST"
}

[[ "$(read_plist CFBundleIdentifier)" == "org.churchcap.desktop" ]]
[[ "$(read_plist CFBundleShortVersionString)" == "0.9.0" ]]
[[ "$(read_plist LSMinimumSystemVersion)" == "13.0" ]]
if [[ -z "$(read_plist NSMicrophoneUsageDescription)" ]]; then
  echo "The macOS microphone usage explanation is missing." >&2
  exit 1
fi

if [[ -d "$PYTHON_FRAMEWORK" ]]; then
  [[ -L "$PYTHON_FRAMEWORK/Python" ]] || { echo "Python.framework/Python must be a symlink." >&2; exit 1; }
  [[ -L "$PYTHON_FRAMEWORK/Resources" ]] || { echo "Python.framework/Resources must be a symlink." >&2; exit 1; }
  [[ -L "$PYTHON_FRAMEWORK/Versions/Current" ]] || { echo "Python.framework/Versions/Current must be a symlink." >&2; exit 1; }
  codesign --verify --strict --verbose=2 "$PYTHON_FRAMEWORK"
  codesign --verify --strict --verbose=2 "$PYTHON_FRAMEWORK/Versions/Current/Python"
fi

if [[ ! -f "$BUNDLED_STYLES" ]]; then
  echo "Bundled web-interface stylesheet is missing: $BUNDLED_STYLES" >&2
  exit 1
fi
if ! cmp -s "$SOURCE_STYLES" "$BUNDLED_STYLES"; then
  echo "Bundled web-interface stylesheet is stale; rebuild the macOS engine before release." >&2
  exit 1
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo "Church Cap macOS application bundle verified: identity, version, macOS target, microphone metadata, bundled web assets, arm64 executables, and code-resource seal are valid."
