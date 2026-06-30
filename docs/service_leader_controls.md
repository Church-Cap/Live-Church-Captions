# Service leader controls

Church Cap includes a denomination-neutral phone/tablet page for a trusted service leader.

The page is intentionally limited to:

- start captions
- stop captions
- blank captions for a private or sensitive moment
- resume captions
- view caption and microphone status
- change the microphone/audio interface while captions are stopped
- view colour-coded caption health derived from the same live timing data used by the operator benchmark
- enable or disable translated captions
- choose Automatic or Manual translated-language availability from resources already configured by the operator

It cannot access transcripts, exports, diagnostics, updates, passwords, performance settings, translation-model installation, or other operator configuration.

The Start, Stop, Pause, and Resume controls use the same status model as the operator page. The active state has a subtle glow, and short action messages explain when captions are starting, stopping, blanked for a private moment, or resuming. If the operator changes the state from the caption computer, the paired page updates during its normal refresh; if the service leader changes the state, the operator page updates in the same way.

## Pair a device

Pairing must begin on the Church Cap computer. Either:

- select **Connect a service leader device** on the operator login page and enter the normal operator password; or
- sign in, open **Service Leader** in the operator menu, and select **Start pairing session**. While a QR is active, the same button becomes **Regenerate pairing QR**.

Show the generated QR to the service leader and scan it with the church-managed phone or tablet.

The QR code:

- is valid for 90 seconds
- can be used once
- contains a random pairing secret, never the operator password
- places the secret in a URL fragment so it is not sent in ordinary server request logs
- is exchanged immediately for a separate restricted cookie

Generating a new QR invalidates any older unused QR without disconnecting devices that have already paired. The operator section can also cancel an unused QR.

## Session security

The service-leader session:

- is separate from the full operator session
- lasts no more than four hours
- expires after two hours without activity
- warns near idle expiry and can explicitly refresh the idle timer
- is stored server-side and disappears when Church Cap restarts
- uses an `HttpOnly`, `SameSite=Strict` cookie
- requires a separate CSRF token and matching request origin for every control action

The dedicated **Service Leader** operator section shows the number of active restricted sessions and whether a pairing window is open. It can generate or replace a QR, cancel an unused QR, open the restricted route, and disconnect all service-leader devices.
Changing the operator password also revokes every service-leader session.

## HTTP and HTTPS

HTTPS remains the strongest option because it protects both credentials and session cookies from network interception. Church Cap never asks the service leader to enter the operator password remotely, which removes the highest-value credential from the HTTP workflow. A captured service-leader cookie would still permit limited control until it expires or is revoked.

For HTTP use:

- use a private WPA2/WPA3 staff or AV network
- do not use open Wi-Fi
- avoid placing the control device on congregation guest Wi-Fi
- restrict the operator port to the trusted subnet where the router/firewall supports it
- never port-forward the operator port to the public internet

For a church-owned phone or tablet, installing the church's `mkcert` certificate authority once can provide HTTPS without requiring certificate setup on audience devices.

## Ports and firewalling

The service-leader page uses the configured operator port, normally TCP `9090`. In secure operator mode, Church Cap listens on that port so paired devices can reach `/service-leader`, but application middleware continues to reject remote access to `/operator` and all other operator routes. Legacy `/pastor` bookmarks redirect to the new route.

On AlmaLinux with `firewalld`, allow port 9090 only from the trusted staff/AV network where practical. The public audience port, normally 8080, can remain available to the audience network.

## Languages

The service leader can only choose languages supported by the translation provider and models already installed by the operator. The provider, model installation, and maximum active-language capacity remain operator-controlled.

The page follows the same availability model as the operator page. If the operator sets Restricted language availability, this page only shows the approved language list. Its language list uses the same admin flag/code chips as the operator language picker, with language-code fallback for platforms that do not render emoji flags reliably:

- **Automatic** lets visitors request any supported installed language. Church Cap translates the most-requested languages up to the operator's active-language limit.
- **Manual** enables only English plus the selected languages. The service leader cannot select more languages than the operator's configured active-language limit.

The searchable list follows the audience client picker pattern: each result shows the native name, English name, and language code, and an empty result is shown when no language matches.

The page refreshes its language resources, selected languages, capacity limit, and audio-device list from the server, so operator-side changes appear without re-pairing the device. Service-leader language and audio changes also appear on the operator page during its normal live-status refresh.

## Caption preview

The caption preview on the service-leader page now observes the same live caption WebSocket used by audience phones, but it is still only a control-page preview. If the page is busy, the device sleeps, or the network reconnects, the preview may appear slightly later than the audience caption page. Use the health card and the audience/client view as the practical performance reference.

The service-leader preview is not counted as an audience viewer and does not affect automatic translated-language demand.

## Caption health

The health card estimates live delay using the latest transcription-pass duration plus the configured caption refresh interval, matching the live-delay calculation used by the operator benchmark:

- under 2.5 seconds: healthy
- 2.5–3.5 seconds: needs attention
- above 3.5 seconds: slow

The improvement guide suggests a faster performance preset, Faster Whisper, a smaller model, fewer translated languages, a direct audio feed, closing competing workloads, and suitable hardware. Performance settings remain operator-only.
