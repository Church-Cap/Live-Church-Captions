#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/org.churchcaptions.local.plist"
launchctl unload "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "Removed Church Cap LaunchAgent."
