"""Safety contracts for the disposable Home Assistant cold-boot fixture."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ha_isolated_boot_smoke as boot


class IsolatedBootFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = self.root / ".storage"
        self.storage.mkdir()
        self.state = self.storage / "core.config_entries"
        self.state.write_text(
            json.dumps(boot.synthetic_entry_store()), encoding="utf-8",
        )

    def test_fixture_has_only_synthetic_entries_and_no_pairings(self):
        entry_state = boot.synthetic_entry_store()
        entries = entry_state["data"]["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual({entry["domain"] for entry in entries},
                         {"homekit", "venta_homekit_native"})
        self.assertTrue(all(entry["source"] == "user" for entry in entries))
        self.assertEqual(
            next(e for e in entries if e["domain"] == "homekit")["disabled_by"],
            "user",
        )
        self.assertNotIn("local_key", json.dumps(entry_state))
        self.assertNotIn("accessory_pin", json.dumps(entry_state))
        self.assertEqual(self.storage.iterdir().__next__().name,
                         "core.config_entries")
        boot._inspect_store(self.root)

    def test_duplicate_entry_is_rejected(self):
        value = json.loads(self.state.read_text())
        value["data"]["entries"].append(value["data"]["entries"][0].copy())
        self.state.write_text(json.dumps(value))
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_reassigned_bridge_is_rejected(self):
        value = json.loads(self.state.read_text())
        for entry in value["data"]["entries"]:
            if entry["domain"] == "venta_homekit_native":
                entry["data"]["bridge_entry_id"] = "different-bridge"
        self.state.write_text(json.dumps(value))
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_duplicate_venta_is_rejected(self):
        value = json.loads(self.state.read_text())
        for entry in value["data"]["entries"]:
            if entry["domain"] == "venta_homekit_native":
                entry["entry_id"] = "ci-duplicate-venta"
        self.state.write_text(json.dumps(value))
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_unexpected_pairing_file_fails_closed(self):
        (self.storage / "homekit.fake").write_text("not-a-real-pairing")
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_missing_entry_file_fails_closed(self):
        self.state.unlink()
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_storage_symlink_fails_closed(self):
        other = self.root / "other"
        other.write_text(self.state.read_text())
        self.state.unlink()
        self.state.symlink_to(other)
        with self.assertRaises(AssertionError):
            boot._inspect_store(self.root)

    def test_no_live_http_endpoint_is_not_reported_ready(self):
        with patch("scripts.ha_isolated_boot_smoke.urlopen", side_effect=OSError()):
            self.assertFalse(boot._http_ready())


if __name__ == "__main__":
    unittest.main()
