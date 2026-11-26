"""Security-scanner regression using temporary, fake tracked-file trees."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "venta_publication_scan", ROOT / "scripts/check_publication_security.py"
)
assert spec is not None and spec.loader is not None
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class PublicationScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fake(self, rel: str, data: bytes) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return rel

    def test_safe_documentation_may_mention_key_names(self):
        name = self.fake("README.md", b"Never share local_key or password.\n")
        self.assertEqual(scanner.scan_paths(self.root, [name]), [])

    def test_secret_value_assignment_is_rejected_without_echo(self):
        name = self.fake("config.yaml", b"local_key: " + b"A" * 30 + b"\n")
        result = scanner.scan_paths(self.root, [name])
        self.assertEqual(len(result), 1)
        self.assertIn("Credential-like content", result[0])
        self.assertNotIn("AAAAAAAA", result[0])

    def test_private_key_header_rejected(self):
        name = self.fake("config.ini", b"-----BEGIN " + b"PRIVATE KEY-----\n")
        self.assertEqual(len(scanner.scan_paths(self.root, [name])), 1)

    def test_long_service_token_signature_rejected(self):
        name = self.fake("example.py", b"token = 'sk-proj-" + b"A" * 36 + b"'")
        self.assertEqual(len(scanner.scan_paths(self.root, [name])), 1)

    def test_html_fixture_is_scanned_for_secrets(self):
        name = self.fake("tests/browser.html", b"<script>const example = \"ghp_" + b"A" * 36 + b"\";</script>")
        self.assertIn("Credential-like content", scanner.scan_paths(self.root, [name])[0])

    def test_hidden_ha_storage_and_secret_files_rejected(self):
        for name in (
            ".storage/core.config_entries",
            "secrets.yaml", ".env.production", "keys/id_ed25519",
            "private.pem", "backups/prod.tar.gz",
        ):
            with self.subTest(name=name):
                findings = scanner.scan_paths(self.root, [name])
                self.assertEqual(len(findings), 1)
                self.assertIn("Private file tracked", findings[0])

    def test_symlink_must_be_reviewed(self):
        self.fake("public.md", b"public")
        (self.root / "alias.md").symlink_to("public.md")
        self.assertIn("symlink", scanner.scan_paths(self.root, ["alias.md"])[0])

    def test_oversized_tracked_file_is_denied(self):
        p = self.root / "oversized.txt"
        with p.open("wb") as output:
            output.truncate(8_000_001)
        self.assertIn("Oversized", scanner.scan_paths(self.root, [p.name])[0])

    def test_binary_asset_is_allowed_without_text_decode(self):
        name = self.fake("assets/icon.png", b"\x89PNG\r\n" + b"private" * 5)
        self.assertEqual(scanner.scan_paths(self.root, [name]), [])

    def test_path_traversal_and_missing_file_rejected(self):
        self.assertEqual(len(scanner.scan_paths(self.root, ["../private"])), 1)
        self.assertEqual(len(scanner.scan_paths(self.root, ["/etc/passwd"])), 1)
        self.assertEqual(len(scanner.scan_paths(self.root, ["missing.md"])), 1)


if __name__ == "__main__":
    unittest.main()
