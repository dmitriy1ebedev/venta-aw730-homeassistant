"""Synthetic-only Home Assistant YAML snapshot and rollback regressions."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import ha_snapshot_rehearsal as recovery


class SnapshotRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "disposable"
        self.config.mkdir()
        self.original = self.config / "configuration.yaml"
        self.original.write_bytes(recovery.BASELINE)
        self.other = self.config / "unrelated.txt"
        self.other.write_bytes(b"unchanged unrelated fixture")
        self.snapshot = self.root / "snapshot"

    def phase(self, name):
        return recovery.rehearse(self.config, self.snapshot, name)

    def test_capture_cutover_restore_is_exact_and_does_not_write_storage(self):
        original_digest = recovery.digest(self.original.read_bytes())
        original_unrelated = self.other.read_bytes()
        self.assertEqual(self.phase("capture")["status"], "PASS")
        self.assertEqual(
            (self.snapshot / "configuration.yaml.original").read_bytes(),
            recovery.BASELINE,
        )
        self.assertEqual(self.phase("cutover")["status"], "PASS")
        self.assertEqual(self.original.read_bytes(), recovery.CUTOVER)
        data = json.loads(
            (self.snapshot / "ui_entry_fixture.json").read_text()
        )
        self.assertEqual(data, recovery.SYNTHETIC_ENTRY)
        self.assertNotIn("local_key", data["data"])
        self.assertFalse((self.config / ".storage").exists())
        self.assertEqual(self.phase("restore")["status"], "PASS")
        self.assertEqual(recovery.digest(self.original.read_bytes()), original_digest)
        self.assertEqual(self.other.read_bytes(), original_unrelated)
        self.assertFalse((self.snapshot / "ui_entry_fixture.json").exists())

    def test_capture_refuses_any_real_or_modified_yaml(self):
        self.original.write_text("homeassistant:\n  name: actual-user\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.phase("capture")
        self.assertFalse(self.snapshot.exists())

    def test_second_capture_cannot_overwrite_backup(self):
        self.phase("capture")
        with self.assertRaises(ValueError):
            self.phase("capture")
        self.assertEqual(self.original.read_bytes(), recovery.BASELINE)

    def test_cutover_without_backup_is_refused(self):
        with self.assertRaises(ValueError):
            self.phase("cutover")
        self.assertEqual(self.original.read_bytes(), recovery.BASELINE)

    def test_cutover_rejects_changed_configuration(self):
        self.phase("capture")
        self.original.write_bytes(recovery.BASELINE + b"# new config\n")
        with self.assertRaises(ValueError):
            self.phase("cutover")
        self.assertFalse((self.snapshot / "ui_entry_fixture.json").exists())

    def test_corrupt_snapshot_refuses_restore(self):
        self.phase("capture")
        self.phase("cutover")
        (self.snapshot / "configuration.yaml.original").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.phase("restore")
        self.assertEqual(self.original.read_bytes(), recovery.CUTOVER)

    def test_changed_cutover_yaml_refuses_restore(self):
        self.phase("capture")
        self.phase("cutover")
        self.original.write_bytes(recovery.CUTOVER + b"# tampered\n")
        with self.assertRaises(ValueError):
            self.phase("restore")

    def test_changed_staged_entry_refuses_restore(self):
        self.phase("capture")
        self.phase("cutover")
        staged = self.snapshot / "ui_entry_fixture.json"
        staged.write_text('{"domain":"foreign"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.phase("restore")

    def test_snapshot_nested_inside_config_is_rejected(self):
        self.snapshot = self.config / "snapshot"
        with self.assertRaises(ValueError):
            self.phase("capture")
        self.assertFalse(self.snapshot.exists())

    def test_configuration_symlink_is_rejected(self):
        source = self.root / "other.yaml"
        source.write_bytes(recovery.BASELINE)
        self.original.unlink()
        self.original.symlink_to(source)
        with self.assertRaises(ValueError):
            self.phase("capture")


if __name__ == "__main__":
    unittest.main()
