#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

chmod +x fix-permissions.sh 2>/dev/null || true
chmod +x setup-macos.sh start-macos.sh start-macos-https.sh setup-linux.sh start-linux.sh update-linux.sh reset-operator-password.sh update-macos.sh 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

echo "Church Cap script permissions repaired."
echo "You can now run:"
echo "  ./setup-macos.sh"
echo "  ./start-macos.sh"
echo "Linux users can run:"
echo "  bash setup-linux.sh"
echo "  ./start-linux.sh"
