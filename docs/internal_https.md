# Internal HTTPS guidance

For local church use, the caption app can run entirely inside the church network.

## Is HTTPS necessary internally?

For the public viewer page, HTTP on an isolated local network may be acceptable because it carries only generated caption text and no user login. The operator page is more sensitive because it has a password and controls the service.

Recommended practical setup:

```text
Viewer page: local HTTP is acceptable for many pilots
Operator page: use HTTPS where practical
Service leader page: use HTTPS on a managed church phone/tablet where practical
Network: keep the app internal, do not port-forward it to the internet
Admin: protect /operator with a strong password
```

## Why local certificates are awkward

Browsers only trust certificates issued by a trusted certificate authority. A local app cannot silently install a trusted certificate on visitors' phones without warnings. That is a browser/platform security feature.

Options:

1. **Self-signed certificate** — encrypted, but visitors see warnings.
2. **mkcert local CA** — good for managed/test devices, but each phone must trust the local CA.
3. **Real domain + DNS-01 certificate** — cleanest no-warning HTTPS without hosting in the cloud.

## Real domain without cloud hosting

You can buy/use a domain such as:

```text
captions.yourchurch.org.uk
```

Then use DNS-01 validation to obtain a Let's Encrypt certificate. The server can still run locally; no cloud instance is required.

Local DNS/router then points:

```text
captions.yourchurch.org.uk -> local Mac mini IP
```

This avoids browser warnings, but it requires domain/DNS management and certificate renewal.

## Offline-first recommendation

For the prototype and church pilots:

```text
- Keep the caption server local only
- Do not expose ports to the internet
- Use a dedicated/guest Wi-Fi rule that allows clients to reach only the caption server port
- Use HTTPS for the operator where practical
- Keep local HTTP as a fallback so Sunday accessibility still works offline
```

The service-leader pairing flow avoids sending the operator password over the network and limits the paired role's permissions. It does not make HTTP encrypted: a capable local attacker could still capture the restricted session cookie. Use private WPA2/WPA3 staff Wi-Fi, short sessions, revocation, and HTTPS where practical.
