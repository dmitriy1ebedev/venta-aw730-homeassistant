"""Cross-process HAP identity fixture guards; never starts Home Assistant."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import ha_homekit_identity_smoke as identity


def synthetic_first() -> dict:
    return {
        "venta_aid": 2,
        "other_aid": 3,
        "venta_shape": (("svc-fan", "venta-fan-v1", 10, (("char", "fan", 11),)),),
        "other_shape": (("svc-native", None, 12, ()),),
        "allocations": {
            "aids": {"humidifier.venta_ci_fake": 2, "humidifier.another_ci_fake": 3},
            "iids": {"2": {"fan": 10}},
        },
    }


class CrossProcessIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_fingerprint_stable_across_json_roundtrip(self):
        initial = synthetic_first()
        saved = json.loads(json.dumps(initial))
        self.assertEqual(
            identity._identity_fingerprint(initial),
            identity._identity_fingerprint(saved),
        )

    def test_fingerprint_catches_aid_or_iid_drift(self):
        original = synthetic_first()
        expected = identity._identity_fingerprint(original)
        for field, change in (
            ("venta_aid", 8),
            ("other_aid", 8),
            ("venta_shape", (("svc-fan", "venta-fan-v1", 101, ()),)),
        ):
            modified = dict(original, **{field: change})
            with self.subTest(field=field):
                self.assertNotEqual(
                    identity._identity_fingerprint(modified), expected
                )

    def test_valid_synthetic_allocation_snapshot(self):
        first = synthetic_first()
        name = self.root / "identity.json"
        content = {
            "schema": "venta-synthetic-identity/v1",
            "fingerprint": identity._identity_fingerprint(first),
            "allocations": first["allocations"],
        }
        name.write_text(json.dumps(content), encoding="utf-8")
        self.assertEqual(identity._read_synthetic_state(name), content)

    def test_rejects_missing_and_malformed_identity_files(self):
        with self.assertRaises(ValueError):
            identity._read_synthetic_state(self.root / "missing.json")
        for text in ("{}", "[]", "not-json", '{"schema":"invalid"}'):
            file = self.root / "malformed.json"
            file.write_text(text, encoding="utf-8")
            with self.subTest(data=text), self.assertRaises(
                (ValueError, json.JSONDecodeError, TypeError)
            ):
                identity._read_synthetic_state(file)

    def test_rejects_symlink_to_another_file(self):
        source = self.root / "real.json"
        source.write_text("{}", encoding="utf-8")
        alias = self.root / "identity.json"
        alias.symlink_to(source)
        with self.assertRaises(ValueError):
            identity._read_synthetic_state(alias)

    def test_rejects_oversized_synthetic_snapshot(self):
        file = self.root / "huge.json"
        file.write_bytes(b"x" * 262145)
        with self.assertRaises(ValueError):
            identity._read_synthetic_state(file)


if __name__ == "__main__":
    unittest.main()
