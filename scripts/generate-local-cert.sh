#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs
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
SAN="DNS:${DNS_NAME},DNS:localhost,IP:127.0.0.1,IP:${LAN_IP}"
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/church-cap-key.pem \
  -out certs/church-cap.pem \
  -days 365 \
  -subj "/CN=${DNS_NAME}" \
  -addext "subjectAltName=${SAN}"
echo "Created self-signed certificate:"
echo "  certs/church-cap.pem"
echo "  certs/church-cap-key.pem"
echo "Hostnames included: ${DNS_NAME}, localhost, ${LAN_IP}"
echo "Browsers will warn unless the certificate/CA is trusted on that device."
