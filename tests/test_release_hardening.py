"""Maintenance 1.0.5 release boundary and sensitive-file exclusions."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_release import (
    COMPONENT, ROOT, ReleaseValidationError, component_files, release_version,
)


class MaintenanceReleaseContracts(unittest.TestCase):
    def test_version_and_bilingual_badges_agree(self):
        self.assertEqual(release_version(expected_tag="v1.0.5"), "1.0.5")
        for name in ("README.md", "README.ru.md"):
            self.assertIn(
                "version-1.0.5-2ea44f", (ROOT / name).read_text(encoding="utf-8")
            )
        self.assertIn("## 1.0.5 (", (ROOT / "CHANGELOG.md").read_text())

    def test_release_contains_no_unreleased_11_features(self):
        source = (ROOT / COMPONENT / "__init__.py").read_text()
        self.assertNotIn("_venta_accessory_factory", source)
        self.assertNotIn("log_diagnostics", source)
        self.assertFalse((ROOT / COMPONENT / "diagnostics.py").exists())

    def test_sensitive_filenames_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            component = root / COMPONENT
            (component / "templates").mkdir(parents=True)
            for name in ("__init__.py", "manifest.json", "services.yaml",
                         "install_localtuya_template.py",
                         "templates/venta_aw730.yaml"):
                (component / name).write_text("safe fixture", encoding="utf-8")
            for name in ("secrets.yaml", "credentials.json", "local_key.txt",
                         "token.json", "private_key.txt", "pairing.json",
                         "entity_registry.json"):
                extra = component / name
                extra.write_text("synthetic", encoding="utf-8")
                with self.subTest(filename=name):
                    with self.assertRaises(ReleaseValidationError):
                        component_files(root)
                extra.unlink()

    def test_candidate_notes_are_not_a_published_release(self):
        notes = (ROOT / "docs/RELEASE_NOTES_v1.0.5.md").read_text()
        self.assertIn("CANDIDATE, NOT RELEASED", notes)
        self.assertIn("release/1.0.5", notes)
        self.assertIn("rollback", notes.lower())


if __name__ == "__main__":
    unittest.main()
