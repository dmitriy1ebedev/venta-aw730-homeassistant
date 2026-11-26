"""AW730 profile: exact, immutable, evidence-bounded and non-destructive."""
import copy
import hashlib
from pathlib import Path
import runpy
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/venta_homekit_native"
MODULE = runpy.run_path(str(COMPONENT / "model_profiles.py"))
AW730 = MODULE["AW730"]
GET = MODULE["get_profile"]
VALIDATE = MODULE["template_errors"]


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        self.raw = (COMPONENT / "templates" / AW730.template).read_bytes()
        self.rows = yaml.safe_load(self.raw)

    def test_exact_aw730_protocol_and_unknown_firmware(self):
        self.assertIs(GET("AW730", "3.4"), AW730)
        self.assertIsNone(AW730.firmware)
        for model, protocol in (("AW735", "3.4"), ("AW730", "3.5"), ("aw730", "3.4"), ("", "3.4"), ("AW730", "")):
            self.assertIsNone(GET(model, protocol))
        self.assertEqual(MODULE["PROFILES"], (AW730,))

    def test_profile_is_immutable(self):
        with self.assertRaises(AttributeError):
            AW730.protocol = "3.5"
        with self.assertRaises(AttributeError):
            AW730.entity("fan").dp = "999"
        self.assertIsNone(AW730.entity("not_a_role"))

    def test_bundled_template_bytes_and_all_mappings(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), AW730.template_sha256)
        self.assertEqual(len(AW730.entities), 18)
        self.assertEqual(len({e.role for e in AW730.entities}), 18)
        self.assertEqual(len({e.dp for e in AW730.entities}), 18)
        self.assertEqual(VALIDATE(AW730, self.rows), ())
        self.assertEqual(AW730.target_dp, AW730.entity("target").dp)
        self.assertEqual(AW730.current_dp, AW730.entity("humidity").dp)
        self.assertEqual(AW730.mode_dp, "24")
        self.assertEqual(AW730.humidity_range, (30, 70))
        self.assertEqual((AW730.fan_levels, AW730.fan_step_percent, AW730.brightness_levels), (5, 20, 8))

    def test_template_drift_fails_closed(self):
        changes = (
            (0, "humidifier", "humidifier_mode_dp", "25"),
            (0, "humidifier", "max_humidity", 80),
            (1, "sensor", "unit_of_measurement", "°F"),
            (3, "button", "entity_category", "config"),
            (10, "select", "restore_on_reconnect", True),
            (10, "select", "is_passive_entity", 0),
            (10, "select", "select_options", {"speed2": 2, "speed1": 1}),
            (11, "select", "id", "999"),
            (16, "number", "min_value", -20),
        )
        for idx, domain, field, value in changes:
            with self.subTest(field=field, idx=idx):
                rows = copy.deepcopy(self.rows)
                rows[idx][domain][field] = value
                self.assertTrue(VALIDATE(AW730, rows))
        self.assertTrue(VALIDATE(AW730, self.rows[:-1]))
        rows = copy.deepcopy(self.rows)
        rows[0], rows[1] = rows[1], rows[0]
        self.assertTrue(VALIDATE(AW730, rows))
        self.assertEqual(VALIDATE(AW730, self.rows), ())

    def test_unverified_resets_do_not_become_control_roles(self):
        self.assertEqual({e.dp for e in AW730.entities if e.access == "unverified"}, {"28", "104", "108"})
        self.assertTrue(all(e.platform == "button" for e in AW730.entities if e.access == "unverified"))
        self.assertEqual({e.role for e in AW730.entities if e.access == "control"}, {"power", "fan", "brightness", "led"})


if __name__ == "__main__":
    unittest.main()
