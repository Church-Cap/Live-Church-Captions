#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Church Cap operator password reset"
echo "This removes the local operator password/session file for your user account."
echo "Afterwards, restart Church Cap and open the operator page to create a new password."
echo ""
echo "Tip: if the server is currently running, press Ctrl+C in that Terminal window first."
read -r -p "Reset the operator password now? [y/N] " answer
case "${answer:-}" in
  y|Y|yes|YES)
    ./scripts/reset-operator-password.sh
    ;;
  *)
    echo "Password reset cancelled."
    ;;
esac
