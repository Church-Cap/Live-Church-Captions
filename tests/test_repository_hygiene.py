import base64
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-repository-hygiene.py"
SPEC = importlib.util.spec_from_file_location("repository_hygiene", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class RepositoryHygieneTests(unittest.TestCase):
    def test_safe_source_and_public_key(self):
        for name in (guard.PUBLIC_KEY, "env.example", ".env.example", "desktop/package-lock.json",
                     "desktop/src-tauri/Cargo.lock", "app/static/flags/4x3/gb.svg"):
            with self.subTest(name=name):
                self.assertEqual(guard.path_issues(name), [])

    def test_secrets_and_generated_paths(self):
        for name in (".env.production", "export.pfx", "export.p12", "private.pem", "secret.key",
                     "data/operator_auth.json", "operator_auth.backup.json", "id_ed25519",
                     "work/local.txt", ".venv-test/bin/python", "desktop/node_modules/a.js",
                     "dist/package.exe", "download.safetensors", ".DS_Store"):
            with self.subTest(name=name):
                self.assertTrue(guard.path_issues(name))

    def test_private_content_is_detected_even_in_allowed_path(self):
        private = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----"
        self.assertTrue(guard.content_issues("innocent.txt", private))
        self.assertTrue(guard.content_issues(guard.PUBLIC_KEY, private))
        minisign = b"untrusted comment: " + b"encrypted secret key"
        self.assertTrue(guard.content_issues("innocent.txt", base64.b64encode(minisign)))

    def test_tokens_and_size(self):
        token = b"ghp_" + b"a" * 36
        self.assertTrue(guard.content_issues("innocent.txt", token))
        self.assertTrue(guard.content_issues("asset.bin", b"x" * (guard.MAX_BYTES + 1)))
        self.assertEqual(guard.content_issues("example.txt", b"YOUR_TOKEN_HERE"), [])

    def test_index_not_worktree_is_scanned_and_history_survives_deletion(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

            def scan(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root,
                                      capture_output=True, text=True)

            git("init")
            git("config", "user.name", "Safety Test")
            git("config", "user.email", "test@example.invalid")
            git("config", "core.hooksPath", str(root / "no-hooks"))
            token = "ghp_" + "a" * 36
            (root / "sample.txt").write_text(token)
            git("add", "sample.txt")
            (root / "sample.txt").write_text("safe working file")
            result = scan()
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(token, result.stdout + result.stderr)
            self.assertEqual(scan("--worktree").returncode, 0)
            git("-c", "commit.gpgsign=false", "commit", "-m", "Synthetic history fixture")
            git("rm", "-f", "sample.txt")
            git("-c", "commit.gpgsign=false", "commit", "-m", "Remove fixture")
            self.assertEqual(scan().returncode, 0)
            self.assertEqual(scan("--history").returncode, 1)

    def test_forced_ignored_file_is_blocked(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text(".env.*\n")
            (root / ".env.production").write_text("EXAMPLE=placeholder\n")
            subprocess.run(["git", "add", "-f", ".env.production"], cwd=root, check=True)
            result = subprocess.run([sys.executable, str(SCRIPT)], cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
