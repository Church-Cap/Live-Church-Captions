#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

chmod +x fix-permissions.sh 2>/dev/null || true
chmod +x setup-macos.sh start-macos.sh start-macos-https.sh reset-operator-password.sh update-macos.sh 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

echo "Church Cap script permissions repaired."
echo "You can now run:"
echo "  ./setup-macos.sh"
echo "  ./start-macos.sh"
