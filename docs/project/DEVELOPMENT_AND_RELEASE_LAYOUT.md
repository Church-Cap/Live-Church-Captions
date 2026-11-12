# Development and release workspace

## Authoritative source

Use the permanent `church-cap/` Git repository. The parent `Church Live Captions/`
directory is not a repository. Keep installers, private evidence and old workspaces
as siblings, never inside source. The September 2026 consolidation preserves the
v0.8.0 GitHub-ready history and existing uncommitted documentation changes. It does
not create a new release or change application behaviour.

Use branches for development (for example `release/v0.9.0`) and tags for accepted
releases. Do not use Finder copies as competing authoritative source folders.
Check `git status` before switching branches, building or committing. Never discard
uncommitted work to make a release appear clean.

## Local safety checks

After cloning, enable the versioned hooks from the repository root:

```sh
git config --local core.hooksPath .githooks
python3 scripts/check-repository-hygiene.py --worktree
python3 scripts/check-repository-hygiene.py --history
```

On Windows use `py -3` or the installed Python 3 executable instead of `python3`.
Python 3.10+ and Git are required. Before replacing an existing `core.hooksPath`,
review and integrate any existing hooks. The consolidated local repository has
these hooks enabled; Git does not enable them automatically for other clones.

The pre-commit hook scans the exact index, including forced ignored files and
partially staged changes. The pre-push hook also scans reachable local history.
The dependency-free GitHub workflow repeats the checks with full fetched history.
It checks prohibited paths, known credential/private-key patterns (including
base64-wrapped Minisign keys), and a 10 MB source-file limit. Findings show only
filenames and reasons. It is not a comprehensive secret detector: inspect diffs,
enable hosting-provider secret protection where available, and treat hooks as
bypassable guardrails. Configure the repository-hygiene CI job as a required check
in GitHub separately; local configuration does not change hosted branch protection.

Keep `env.example`, build manifests, lockfiles, source assets, legal notices and
the updater **public** key tracked. Do not commit `.env` variants, credential
exports, runtime authentication/configuration files, logs, models, installers,
virtual environments or caches. Private updater keys and signing certificates stay
in their existing protected external storage/credential store. Never copy them to
a Windows build handoff, source ZIP, public issue or release-evidence attachment.

Ignore rules do not remove previously tracked files. If an actual credential has
been exposed, stop publication and rotate/revoke it; deleting the file alone does
not remove it from Git history. Historical scans cover locally reachable objects;
the inherited repository is shallow, so a full remote-history audit requires a
separate fetch/review. Reflogs and unreachable objects are not covered by the guard.

## Platform builds

1. Test and review the intended source commit. Record its full commit ID and require
   a clean working tree for release builds.
2. Build Mac and Windows from that same commit. A Windows build checkout may use a
   short path such as `C:\ChurchCapBuild`; its folder name is not the application
   version. Never copy its `target/`, `node_modules/` or local credentials into the
   authoritative repository. Changes made on Windows must return as reviewed source
   commits/patches, not by overlaying whole folders.
3. Existing scripts may continue writing ignored `dist/`, `build/` and
   `desktop/src-tauri/target/` outputs. Do not change those paths merely to tidy the
   workspace. Source virtual environments remain local and disposable.
4. Follow the existing desktop update release runbook for signing, notarisation and
   platform testing. Updater signing and OS code signing are separate checks.
5. Copy accepted downloads to sibling `releases/vX.Y.Z/{macos,windows,linux}/`.
   Preserve public download filenames. Keep each signature adjacent to its artifact.
   Generate a root SHA256SUMS file using paths relative to that release directory.
6. Keep commit IDs, platform/toolchain records, test reports and notarisation records
   under sibling `release-evidence/vX.Y.Z/`. Review evidence before sharing it.
7. Upload only intended public release assets. Never upload the whole workspace.
   Preserve existing published v0.8.0 artifacts byte-for-byte; v0.9.0 needs new builds.

Original pre-consolidation folders are retained in the sibling archive. They are
historical evidence, not active build sources. No signing keys are moved as part of
consolidation. The v0.9.0 application changes and release packaging remain separate from that historical workspace move.
