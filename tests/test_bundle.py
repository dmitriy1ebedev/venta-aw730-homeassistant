"""Regression checks for the bundled LocalTuya template and its installer."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PART = ROOT / "custom_components" / "venta_homekit_native"
SOURCE = PART / "templates" / "venta_aw730.yaml"
HELPER = PART / "install_localtuya_template.py"


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("venta_template_installer", HELPER)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_brand_images(self):
        from struct import unpack
        for name, width in (("icon.png", 256), ("icon@2x.png", 512)):
            raw = (PART / "brand" / name).read_bytes()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(unpack(">I", raw[16:20])[0], width)

    def test_corrected_units(self):
        entities = yaml.safe_load(SOURCE.read_text())
        self.assertEqual(len(entities), 18)
        sensors = {v["friendly_name"]: v for e in entities for k, v in e.items() if k == "sensor"}
        for name in ("Service", "Cleaning", "Filter"):
            self.assertEqual(sensors[name]["unit_of_measurement"], "d")
        self.assertEqual(sensors["PM2.5"]["unit_of_measurement"], "μg/m³")
        self.assertNotIn("device_class", sensors["Water Level"])
        self.assertNotIn("local_key", SOURCE.read_text())

    def test_installer_creates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            self.assertEqual(self.module.install(config), "installed")
            self.assertEqual((directory / "venta_aw730.yaml").read_bytes(), SOURCE.read_bytes())
            self.assertEqual(self.module.install(config), "already installed")

    def test_installer_preserves_edited_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            destination = directory / "venta_aw730.yaml"
            destination.write_text("user customized template\n")
            with self.assertRaises(RuntimeError):
                self.module.install(config)
            self.assertEqual(destination.read_text(), "user customized template\n")
            self.assertEqual(self.module.install(config, replace=True), "installed")
            backups = list(directory.glob("venta_aw730.yaml.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "user customized template\n")

    def test_installer_requires_localtuya(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self.module.install(Path(tmp))

    def test_sync_without_localtuya_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("skipped", self.module.sync_managed_template(Path(tmp)))

    def test_sync_installs_and_records_managed_hash(self):
        import hashlib
        import json
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            self.assertEqual(self.module.sync_managed_template(config), "installed")
            destination = directory / "venta_aw730.yaml"
            self.assertEqual(destination.read_bytes(), SOURCE.read_bytes())
            marker = config / ".storage" / self.module.MARKER
            self.assertEqual(
                json.loads(marker.read_text())["destination_sha256"],
                hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            )
            self.assertEqual(self.module.sync_managed_template(config), "already current")

    def test_sync_legacy_template_copies_and_backs_up(self):
        legacy = SOURCE.read_text().replace("unit_of_measurement: μg/m³", "unit_of_measurement: ug/m3").replace(
            "unit_of_measurement: d", "unit_of_measurement: days"
        )
        legacy = legacy.replace(
            "friendly_name: Water Level\\n    entity_category: diagnostic\\n    unit_of_measurement: '%'\\n",
            "friendly_name: Water Level\\n    entity_category: diagnostic\\n    unit_of_measurement: '%'\\n    device_class: duration\\n",
        )
        self.assertTrue(self.module._only_known_legacy_differences(
            legacy.encode(), SOURCE.read_bytes()
        ))
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            destination = directory / "venta_aw730.yaml"
            destination.write_text(legacy)
            self.assertIn("updated", self.module.sync_managed_template(config))
            self.assertEqual(destination.read_bytes(), SOURCE.read_bytes())
            backups = list(directory.glob("venta_aw730.yaml.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), legacy)

    def test_sync_preserves_edited_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            self.module.sync_managed_template(config)
            destination = directory / "venta_aw730.yaml"
            changed = destination.read_text().replace(
                "friendly_name: Temperature", "friendly_name: My Temperature"
            )
            destination.write_text(changed)
            self.assertIn("modified template preserved", self.module.sync_managed_template(config))
            self.assertEqual(destination.read_text(), changed)
            self.assertFalse(list(directory.glob("venta_aw730.yaml.*.bak")))

    def test_sync_upgrades_tracked_previous_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            self.module.sync_managed_template(config)
            destination = directory / "venta_aw730.yaml"
            old_content = SOURCE.read_bytes().replace(b"friendly_name: Temperature", b"friendly_name: Temp")
            destination.write_bytes(old_content)
            # Mimic a previous Marketplace release's checksum state.
            self.module._save_managed_digest(config, old_content)
            self.assertIn("updated", self.module.sync_managed_template(config))
            self.assertEqual(destination.read_bytes(), SOURCE.read_bytes())
            self.assertEqual(len(list(directory.glob("venta_aw730.yaml.*.bak"))), 1)

    def test_sync_does_not_follow_template_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            directory = config / "custom_components" / "localtuya" / "templates"
            directory.mkdir(parents=True)
            real = config / "external.yaml"
            real.write_text("untouched")
            (directory / "venta_aw730.yaml").symlink_to(real)
            self.assertIn("skipped", self.module.sync_managed_template(config))
            self.assertEqual(real.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
