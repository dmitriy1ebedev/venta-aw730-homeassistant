"""Release packaging, integrity, and isolated install-layout smoke tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_release import (
    COMPONENT, ROOT, ReleaseValidationError, build_archive,
    component_files, release_version,
)


class ReleasePackageTests(unittest.TestCase):
    def test_manifest_changelog_and_tag_agreement(self):
        version = release_version()
        self.assertEqual(version, "1.2.0")
        self.assertEqual(release_version(expected_tag="v" + version), version)
        with self.assertRaises(ReleaseValidationError):
            release_version(expected_tag="v9.9.9")

    def test_reproducible_archive_and_no_accidental_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.zip", Path(tmp) / "b.zip"
            a = build_archive(first)
            b = build_archive(second)
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["sha256"], hashlib.sha256(first.read_bytes()).hexdigest())
            names_expected = [p for _src, p in component_files()]
            with zipfile.ZipFile(first) as z:
                names = z.namelist()
                self.assertEqual(names, names_expected)
                self.assertTrue(all(name.startswith(COMPONENT.as_posix() + "/") for name in names))
                self.assertFalse(any(".storage" in name or "secrets" in name.lower() for name in names))
                self.assertEqual(json.loads(z.read((COMPONENT / "manifest.json").as_posix()))["version"], release_version())
            with self.assertRaises(FileExistsError):
                build_archive(first)

    def test_isolated_install_layout_without_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive_path = base / "candidate.zip"
            build_archive(archive_path)
            config = base / "config"
            target = config / "custom_components" / "localtuya" / "templates"
            target.mkdir(parents=True)
            # Only extract our self-produced archive; no external untrusted zip.
            with zipfile.ZipFile(archive_path) as archive:
                self.assertTrue(all(n.startswith("custom_components/venta_homekit_native/") for n in archive.namelist()))
                archive.extractall(config)
            script = config / COMPONENT / "install_localtuya_template.py"
            spec = importlib.util.spec_from_file_location("venta_test_release_installer", script)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.sync_managed_template(config), "installed")
            self.assertEqual(module.sync_managed_template(config), "already current")
            template = (config / COMPONENT / "templates" / "venta_aw730.yaml").read_bytes()
            self.assertEqual((target / "venta_aw730.yaml").read_bytes(), template)
            marker = config / ".storage" / module.MARKER
            self.assertEqual(json.loads(marker.read_text())["destination_sha256"], hashlib.sha256(template).hexdigest())

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component = root / COMPONENT
            component.mkdir(parents=True)
            for name in ("__init__.py", "services.yaml", "install_localtuya_template.py", "templates/venta_aw730.yaml", "manifest.json"):
                file = component / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("placeholder")
            (component / "link").symlink_to(component / "manifest.json")
            with self.assertRaises(ReleaseValidationError):
                component_files(root)


if __name__ == "__main__":
    unittest.main()
