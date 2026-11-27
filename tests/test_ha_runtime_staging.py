"""Safety checks for staging a release into a disconnected HA runtime."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_release import COMPONENT, ReleaseValidationError, build_archive
from scripts.stage_ha_runtime import FAKE_HA_CONFIG, stage


class HARuntimeStagingTests(unittest.TestCase):
    def test_stage_test_config_only_and_refuse_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source.zip"
            build_archive(archive)
            config = root / "isolated-config"
            report = stage(archive, config)
            self.assertEqual(report["component_version"], "1.3.0")
            self.assertTrue(report["no_device_credentials"])
            self.assertTrue((config / COMPONENT / "manifest.json").exists())
            self.assertEqual((config / "configuration.yaml").read_text(), FAKE_HA_CONFIG)
            self.assertFalse((config / ".storage").exists())
            self.assertNotIn("local_key:", FAKE_HA_CONFIG)
            with self.assertRaises(ReleaseValidationError):
                stage(archive, config)

    def test_stage_rejects_unexpected_archive_files_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "bad.zip"
            with zipfile.ZipFile(invalid, "w") as z:
                z.writestr("custom_components/venta_homekit_native/manifest.json", "{}")
                z.writestr("../secrets.yaml", "token: fake")
            config = root / "should-not-exist"
            with self.assertRaises(ReleaseValidationError):
                stage(invalid, config)
            self.assertFalse(config.exists())


if __name__ == "__main__":
    unittest.main()
