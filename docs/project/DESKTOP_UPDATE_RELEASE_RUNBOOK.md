# Church Cap Desktop Update Release Runbook

Last updated: 2026-10-21

Church Cap uses Tauri's mandatory updater signature independently of operating-system signing. Apple Developer ID and notarization remain required for the Mac release. Windows Authenticode is recommended for reputation and SmartScreen, but the user accepted deferring it for v0.8.0; a Tauri signature is still mandatory before Church Cap may install a Windows package through its in-app updater.

## Channels and releases

- All supported platform downloads use one GitHub tag/release, `vX.Y.Z`.
- Mac desktop channel: `updates/desktop/darwin-aarch64/latest.json`.
- Windows desktop channel: `updates/desktop/windows-x86_64/latest.json`.
- Linux CLI uses the same release's `Church-Cap-Linux-CLI.tar.gz` and `.sha256` assets through its CLI updater, not Tauri.
- Appliance remains a Linux deployment profile unless a separately installed image is introduced later.

The version inside every build remains normal semantic version text such as `0.9.0`, and the matching public release tag is `v0.9.0`. Mac and Windows retain independent signed manifests even though their artifacts share one release. Publish each manifest only after its platform artifact is anonymously downloadable and verified. A platform manifest may remain on the previous tested version if that platform's new artifact is not ready; never point it at a missing or unverified asset.

## Updater signing key

The committed public key is `packaging/updater/church-cap-updater-public.key` and is embedded in `desktop/src-tauri/tauri.conf.json`. The private key must never enter the repository, a release asset, normal logs, diagnostics, or a shared project folder.

On the current release Mac, the encrypted private key is stored outside this project in an owner-only release folder and its password is protected by the macOS Keychain service `Church Cap Tauri Updater Signing Key`.

The v0.8.0 updater key pair used public-key ID `BF1E020A4490108A`. Its encrypted private-key file could not be recovered even though its password remained in Keychain. On 21 September 2026, before publishing v0.9.0, the updater trust root was deliberately rotated to public-key ID `A4BFB5872F60E7CF`. Existing v0.8.0 desktop applications cannot verify artifacts signed by the replacement key, so v0.8.0 users require one manual DMG or Windows-installer upgrade. On 21 October 2026, still before v0.9.0 was published, replacement key `A4BFB5872F60E7CF` was itself retired: its encrypted private-key file was intact, but no recorded password unlocked it. No released application ever trusted that key. The current trust root is public-key ID `25BF3CCF4B6CBB01`, created on the release Mac with an immediate signature and tamper-rejection probe, both with the password typed and read from Keychain. v0.9.0 and later releases use `25BF3CCF4B6CBB01` for automatic signed updates. Every v0.9.0 Mac or Windows candidate containing the v0.8.0 public key or `A4BFB5872F60E7CF` is superseded and must not be published; Linux CLI releases are unaffected.

1. Back up the encrypted private key to an independently encrypted, access-controlled location.
2. Back up the password in the project owner's password manager, separately from the key backup.
3. Restore both into an isolated directory and perform a signing probe.
4. Record who controls recovery access. Losing either item prevents existing installations from trusting future updates.

CI should receive the private key and password only through protected release-environment secrets. Unsigned build/test jobs must not receive them.

## Mac release order

1. Build the frozen engine and release-profile app from locked inputs on Apple Silicon.
2. Set `CHURCH_CAP_CODESIGN_IDENTITY` to the exact Keychain identity, `CHURCH_CAP_CODESIGN_IDENTITY_SHA1` to its 40-character certificate fingerprint, and `CHURCH_CAP_NOTARY_PROFILE` to the validated `notarytool` profile. The fingerprint selector prevents duplicate certificates with the same Apple display name from making `codesign` ambiguous while authority verification still uses the human-readable Developer ID name.
3. Run `scripts/release/sign-macos-app.sh`. It signs nested code from the inside out, verifies Developer ID, Team ID, secure timestamp, Hardened Runtime, and production entitlements, then deliberately defers Gatekeeper until notarization.
4. Run `scripts/release/notarize-macos-app.sh`. It submits a metadata-preserving ZIP, retains Apple's submission/log evidence, staples the accepted ticket to the app, and requires Gatekeeper acceptance.
5. Run `scripts/release/build-macos-updater-artifact.sh` against that exact stapled app. It rejects ad-hoc/no-Team-ID apps, creates `Church-Cap-vX.Y.Z-macOS-Apple-Silicon.app.tar.gz`, and invokes `sign-updater-artifact.sh` for its `.sig`.
6. Run `scripts/release/build-macos-dmg.sh` to create the human-facing DMG from the same stapled app. The production builder rejects internal naming, version drift, ad-hoc/no-Team-ID input, or an unstapled app.
7. Run `scripts/release/notarize-macos-dmg.sh` to sign the DMG, submit it, retain Apple's evidence, staple it, and require the final Gatekeeper assessment.
8. Upload the DMG, updater archive, `.sig`, checksums, notices, SBOM, provenance, and release notes to the draft `vX.Y.Z` release alongside the other platform assets.
9. Run clean-machine/quarantine tests, publish the unified release, and confirm the updater archive URL is anonymously downloadable.
10. Generate `updates/desktop/darwin-aarch64/latest.json` with `generate-desktop-update-manifest.py`, review its URL/version/signature, then publish that manifest in a later commit.

The v0.8.0 release Mac has a user-verified `Developer ID Application` identity for Team ID `VCFSA9YLF5`, certificate fingerprint `27744BF4CE7F2729EE04284CEB4579E6244ED9C3`, and a validated `Church Cap Notary` Keychain profile. Certificate names and fingerprints are public release metadata; no private key, certificate export, Apple password, or app-specific password belongs in this project or its logs.

Notarization submissions `4b5840ab-f1e6-445b-b2c0-93bf6452afb2` (app) and `d1c1608c-a4aa-4a79-9098-c80eef3351df` (DMG) belong to earlier updater-key-rotation candidates built before the final v0.9.0 source; they are superseded evidence and must not be published. The final v0.9.0 submission identifiers are recorded with the release evidence, not here. Submission identifiers are release evidence, not credentials.

## Windows release order

Use the matching order on a clean Windows x64 builder: frozen-engine verification, NSIS build, Authenticode signing and verification when required, Tauri `.sig`, clean-machine tests, upload to the shared `vX.Y.Z` release, confirm the asset URL, then publish `updates/desktop/windows-x86_64/latest.json` in a later commit. The shared-core and wrapper source-of-truth rules are in `CROSS_PLATFORM_ARCHITECTURE.md`; the current native build procedure is in `WINDOWS_V0.9.0_BUILD_HANDOFF.md`.

## Linux release order

Build and validate `Church-Cap-Linux-CLI.tar.gz`, upload it and `Church-Cap-Linux-CLI.tar.gz.sha256` to the same `vX.Y.Z` release, then verify both URLs. The Linux updater selects GitHub's latest published non-prerelease and downloads only those two curated assets. It preserves the local environment and user data, stages and validates the replacement, and retains rollback data if replacement fails.

## Unified publication order

1. Create the `vX.Y.Z` release as a draft.
2. Upload every ready human-facing installer, updater artifact, `.sig`, and checksum.
3. Complete clean-machine checks against the exact uploaded files.
4. Publish the GitHub Release and confirm anonymous downloads.
5. Generate and commit the Mac and Windows manifests last. This commit is the point at which installed desktop applications can discover the new version.

## Required update acceptance

A release is not complete until the previous installed version:

- reports the correct new version and release notes;
- rejects missing, altered, and wrong-key signatures;
- refuses installation while captions are live, including when captions start during download;
- preserves passwords, settings, models, logs, and privacy choices;
- stops its owned engine cleanly only after verification;
- installs, relaunches, passes compatible `/health`, and reports the new running version;
- recovers honestly from network loss, full disk, locked files, installer failure, and failed post-update health.

As of 20 September 2026, both public desktop manifest URLs return HTTP 404. Keep them unpublished for v0.8.0 because that release trusts the retired key and cannot verify a replacement-key signature. Operators must install v0.9.0 manually once; the unchanged `org.churchcap.desktop` identifier and v0.9.0's one-time legacy-root migration preserve existing application data. After each matching v0.9.0 artifact is live and verified, publish that platform's signed manifest at the existing endpoint. That activates automatic discovery for v0.9.0 and later installations. Never publish a placeholder manifest or one that names a draft, missing, unsigned, wrong-key, or superseded artifact.

v0.8.0 applications poll the same manifest endpoints. Once a v0.9.0 or later manifest is published, an installed v0.8.0 app that checks for updates will be offered that version, show the manifest `notes`, and then refuse the download at signature verification without replacing the installed app. Because tauri-plugin-updater 2.10.1 reports download completion before it verifies the signature, the v0.8.0 app downloads the full archive, may briefly show "Update signature verified.", and then reports that it could not download or verify the update; the installed app is unchanged. Every manifest published while v0.8.0 installations may remain must therefore be generated with `--notes-file` text that tells v0.8.0 users to download and run the release installer manually. A suitable note is: "Church Cap v0.9.0 uses a new updater signing key. If you are using v0.8.0, download and run the v0.9.0 installer from the GitHub release page; in-app installation from v0.8.0 cannot verify this update and will not change your installation."
