#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs
if ! command -v mkcert >/dev/null 2>&1; then
  echo "mkcert is not installed. Install it with: brew install mkcert nss"
  exit 1
fi
HOSTNAME_LOCAL="$(scutil --get LocalHostName 2>/dev/null || echo church-cap)"
DNS_NAME="${HOSTNAME_LOCAL}.local"
LAN_IP="$(python3 - <<'PY'
import socket
try:
    s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8',80))
    print(s.getsockname()[0])
    s.close()
except Exception:
    print('127.0.0.1')
PY
)"
mkcert -install
mkcert \
  -cert-file certs/church-cap.pem \
  -key-file certs/church-cap-key.pem \
  "${DNS_NAME}" localhost 127.0.0.1 "${LAN_IP}"
echo "Created mkcert certificate: certs/church-cap.pem"
echo "This Mac should trust it. Other phones/computers must trust the mkcert root CA to avoid warnings."
echo "Run HTTPS with: ./start-macos-https.sh"
