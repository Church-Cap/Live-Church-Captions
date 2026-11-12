# Desktop update channels

The installed Tauri supervisor reads one independently versioned manifest:

- `darwin-aarch64/latest.json` for the Apple Silicon Mac release;
- `windows-x86_64/latest.json` for the Windows x64 release.

Mac, Windows, and Linux artifacts are published together in one `vX.Y.Z` GitHub Release. The desktop manifests remain separate so each installed wrapper downloads only its own signed artifact. Linux and Appliance releases continue to use their CLI update route and must not publish a Tauri desktop manifest.

`latest.json` files are release outputs, not hand-written metadata. Generate one only after its platform artifact and `.sig` exist:

```text
python3 scripts/release/generate-desktop-update-manifest.py \
  --version 0.9.0 \
  --target darwin-aarch64 \
  --artifact-url https://github.com/Church-Cap/Live-Church-Captions/releases/download/v0.9.0/Church-Cap-v0.9.0-macOS-Apple-Silicon.app.tar.gz \
  --signature-file dist/Church-Cap-v0.9.0-macOS-Apple-Silicon.app.tar.gz.sig \
  --notes-file docs/project/V0.9.0_RELEASE_NOTES.md
```

Commit and publish each generated platform manifest only after its referenced GitHub Release asset is anonymously downloadable and its checksum and updater signature have been reverified. The public v0.8.0 desktop channels have no manifest and trust the retired updater key, so v0.8.0 users must install v0.9.0 manually once. Publishing verified v0.9.0 manifests signed by replacement key `25BF3CCF4B6CBB01` activates automatic discovery for v0.9.0 and later installations; it cannot activate the v0.8.0 launcher.
