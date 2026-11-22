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


if __name__ == "__main__":
    unittest.main()
