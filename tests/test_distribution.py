import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "custom_components" / "venta_homekit_native" / "__init__.py"

class DistributionTests(unittest.TestCase):
    def test_syntax(self):
        ast.parse(FILE.read_text())
    def test_hassfest_contract(self):
        source = FILE.read_text()
        self.assertIn("CONFIG_SCHEMA = vol.Schema(", source)
        self.assertIn('hass.services.async_register(DOMAIN, "reload_venta"', source)
        import yaml
        services = yaml.safe_load((FILE.parent / "services.yaml").read_text())
        self.assertIn("reload_venta", services)

    def test_manifest(self):
        d = json.loads((FILE.parent / "manifest.json").read_text())
        self.assertEqual(d["domain"], "venta_homekit_native")
    def test_hacs_json(self):
        self.assertTrue(json.loads((ROOT / "hacs.json").read_text())["name"])
    def test_no_installation_identifiers(self):
        s = FILE.read_text()
        for forbidden in ('192.168.', 'local_key', 'moika_', 'dmitriy'):
            self.assertNotIn(forbidden, s)
        self.assertIn('ENTITY = BRIDGE_ENTRY = FAN = LED', s)
    def test_valid_auto_values(self):
        s = FILE.read_text()
        self.assertIn('valid_values={"Auto": 0, "Humidifier": 1}', s)
        self.assertIn('unique_id="venta-auto-mode-v1"', s)
    def test_config_required(self):
        self.assertIn("configuration.yaml must define all seven options", FILE.read_text())
if __name__ == "__main__":
    unittest.main()
