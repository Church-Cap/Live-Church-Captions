# Church Cap Linux CLI package

Church Cap v0.9.0 for Linux is a curated, architecture-neutral source archive. It contains the shared browser application and the package-manager-aware Linux setup, start, update, CUDA, translation, spoken-language, password-recovery, and confirmed factory-reset helpers. It intentionally contains no Tauri wrapper, macOS/Windows artifacts or named updater scripts, Finder `.DS_Store` metadata, repository history, tests, build caches, or developer toolchains.

Build on any platform:

```text
python scripts/release/build-linux-cli-release.py
python scripts/release/check-linux-cli-release.py dist/releases/Church-Cap-Linux-CLI.tar.gz
```

The archive must still pass clean installation and upgrade acceptance on representative Debian/Ubuntu and RHEL/AlmaLinux-family x86_64 systems before publication.

Release candidates are recorded in the external `release-evidence/vX.Y.Z/` directory rather than hard-coded here. The build selects the unified `vX.Y.Z` GitHub Release and downloads only the curated Linux archive and checksum. The build is deterministic and the validator rejects `update-macos.sh`, `.DS_Store`, links, unsafe paths, desktop/build trees, or missing shared engine/update/project-local Python helpers. Clean startup and update acceptance on representative Debian/Ubuntu and RHEL/AlmaLinux-family systems remain release gates.
