# Security, privacy, HTTPS, and local networking

This prototype is designed to be local-first: audio is captured on the church computer, captions are served on the local network, and guests only need a browser.

## Operator login

The public caption pages are open so visitors can scan a QR code and read captions. The operator controls are protected by a password.

On first startup, Church Cap opens `/setup` so the operator can create a local password. The password is stored as a salted hash in the per-user data folder, not in the project folder. `OPERATOR_PASSWORD` and `SESSION_SECRET` in `.env` are optional legacy/development overrides; for normal church use, prefer the first-run setup page.

Protected pages/routes include:

```text
/operator
/transcript.txt
/transcript.vtt
/transcript.srt
/transcript.json
/api/start
/api/stop
/api/clear
/api/audio-devices
/api/audio-device
/api/privacy
/api/profanity-filter
/api/translation
/api/sensitive-on
/api/sensitive-off
```

Audience caption pages remain open:

```text
/
/display
/obs
/qr.png
/qr-ip.png
/api/languages
/ws/captions
```

## Sensitive moment mode

Use **Blank / pause captions** before private prayer, pastoral details, safeguarding disclosures, testimony, or anything that should not be displayed or retained.

When enabled:

- new captions are not shown to viewers
- new captions are not saved to transcript history
- audience screens show a private-moment message

Use **Resume captions** when the public service continues.

## Transcript retention

The operator page lets you choose whether transcript history is saved and how long to keep it. Current options include:

- do not retain history
- 30 minutes
- 2 hours
- 1 day
- 7 days

For privacy, avoid storing audio by default. Church Cap does not store audio. When transcript saving is enabled, caption text is retained for the configured window in a small local transcript cache under the per-user data folder. The cache is encrypted at rest when the `cryptography` dependency is installed and records the retention window that applied when it was saved. A fresh app start begins with an empty visible session transcript, then prunes the saved cache on startup using the saved retention window. Current-session transcript export is operator-only and shows a privacy warning because exported files may contain names, pastoral details, prayer requests, testimony, or other sensitive information. Sensitive moment mode suppresses transcript retention and export for that period, flushes the live transcription buffer, and includes a short buffered-audio drain window after captions resume. Clearing the transcript or setting retention to **Do not retain history** deletes the retained transcript cache.

On macOS, runtime settings and operator auth are stored under:

```text
~/Library/Application Support/Church Cap/data/
```

On Windows, they are stored under:

```text
%APPDATA%\Church Cap\data\
```

Older project-local files from `data/` are migrated there when needed. Transcript retention is enforced when captions are written, when settings change, and when the app starts; if every retained caption is older than the retention window saved with that cache, the transcript cache is deleted. The operator page includes **Open transcript folder**, which opens this per-user data folder in Finder on macOS or File Explorer on Windows when used from the Church Cap computer.

## HTTPS / local certificate

For local testing, plain HTTP is easiest:

```text
http://192.168.1.50:8080
```

For HTTPS, you need a certificate trusted by the devices using it. There are two practical routes.

### Option A: mkcert for testing

`mkcert` creates local development certificates. It is useful for testing on your own devices, but you still need to install/trust its local CA on each device that will access captions.

```bash
brew install mkcert nss
mkcert -install
mkdir -p certs
mkcert -cert-file certs/church-cap.local.crt -key-file certs/church-cap.local.key church-cap.local localhost 127.0.0.1
./scripts/run-dev-https.sh
```

Then open:

```text
https://church-cap.local:8443
```

### Option B: self-signed certificate

You can generate a self-signed certificate:

```bash
./scripts/generate-local-cert.sh
./scripts/run-dev-https.sh
```

Browsers will warn unless the certificate is trusted on that device. This is acceptable for development, but not ideal for visitors.

## Local hostname: `church-cap.local`

There are several ways to make `church-cap.local` work.

### Easiest for Mac/iPhone networks: mDNS / Bonjour

Many Apple devices can resolve `.local` hostnames via Bonjour. Set the Mac mini computer name to something like `caption`, then try:

```text
http://church-cap.local:8080
```

### Router/DNS reservation

On the church router:

1. Reserve a fixed IP for the caption computer.
2. Add a local DNS record such as `church-cap.local` or `captions.church.lan` pointing to that IP.
3. Set `PUBLIC_BASE_URL` in `.env`, for example:

```env
PUBLIC_BASE_URL=http://church-cap.local:8080
```

If using HTTPS:

```env
PUBLIC_BASE_URL=https://church-cap.local:8443
```

## Network isolation / guest Wi-Fi rules

A good church setup is:

```text
Caption Mac mini: wired Ethernet on trusted AV/admin network
Audience phones: church guest Wi-Fi
Firewall rule: guest Wi-Fi may access caption server port 8080/8443 only
Firewall rule: guest Wi-Fi cannot access other internal devices
Operator/admin device: trusted network, or same device running the app
```

Minimum rule:

```text
Allow guest Wi-Fi → caption server IP → TCP 8080 or 8443
Block guest Wi-Fi → other LAN devices
```

Do not expose the caption server directly to the public internet unless you have reviewed authentication, HTTPS, logging, transcript retention, and cloud/security implications.

## Suggested pilot defaults

```env
PUBLIC_BASE_URL=http://church-cap.local:8080
TRANSCRIPT_SAVING_ENABLED=true
TRANSCRIPT_RETENTION_MINUTES=120
TRANSLATION_ENABLED=false
```

During sensitive moments, press **Blank / pause captions**.
