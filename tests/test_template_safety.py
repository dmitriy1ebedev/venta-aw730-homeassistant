"""P02.4 — non-destructive LocalTuya template upgrade/restore contracts.

All configuration entries below are synthetic and live only in temporary
directories; never read a real Home Assistant .storage directory or Tuya key.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "custom_components/venta_homekit_native/install_localtuya_template.py"
SOURCE = ROOT / "custom_components/venta_homekit_native/templates/venta_aw730.yaml"


class SafeTemplateMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("venta_p024_template", HELPER)
        assert spec and spec.loader
        cls.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.installer)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name)
        self.localtuya_dir = self.config / "custom_components/localtuya/templates"
        self.localtuya_dir.mkdir(parents=True)
        self.dest = self.localtuya_dir / "venta_aw730.yaml"
        self.marker = self.config / ".storage" / self.installer.MARKER
        self.entries = self.config / ".storage/core.config_entries"
        self.registry = self.config / ".storage/core.entity_registry"
        self.entries.parent.mkdir(parents=True, exist_ok=True)
        self.entries.write_bytes(
            b'{"data":{"entries":[{"entry_id":"fixture-existing-localtuya",'
            b'"device_id":"synthetic-device",'
            b'"domain":"localtuya","version":1}]}}\n'
        )
        self.registry.write_bytes(
            b'{"data":{"entities":[{"entity_id":"humidifier.fixture_venta",'
            b'"unique_id":"fixture-existing-entity-001",'
            b'"config_entry_id":"fixture-existing-localtuya"}]}}\n'
        )
        self.before = (self.entries.read_bytes(), self.registry.read_bytes())
        self.fresh = SOURCE.read_bytes()

    def assert_no_config_migration(self):
        self.assertEqual(
            (self.entries.read_bytes(), self.registry.read_bytes()), self.before,
            "template helper must not rewrite existing LocalTuya config entries or IDs",
        )
        self.assertEqual(
            json.loads(self.registry.read_text())["data"]["entities"][0]["unique_id"],
            "fixture-existing-entity-001",
        )

    def test_first_install_and_second_start_are_non_destructive(self):
        self.assertEqual(self.installer.sync_managed_template(self.config), "installed")
        self.assertEqual(self.installer.sync_managed_template(self.config), "already current")
        self.assertEqual(self.dest.read_bytes(), self.fresh)
        self.assertEqual(
            json.loads(self.marker.read_text())["destination_sha256"],
            hashlib.sha256(self.fresh).hexdigest(),
        )
        self.assert_no_config_migration()

    def test_tracked_old_copy_backed_up_and_can_be_restored(self):
        old = self.fresh.replace(b"friendly_name: Temperature", b"friendly_name: Earlier Temperature")
        self.dest.write_bytes(old)
        self.installer._save_managed_digest(self.config, old)
        self.assertEqual(
            self.installer.sync_managed_template(self.config),
            "updated (previous copy backed up)",
        )
        backups = list(self.localtuya_dir.glob("venta_aw730.yaml.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), old)
        self.assertEqual(self.dest.read_bytes(), self.fresh)
        self.assert_no_config_migration()
        # Isolated rollback: restore only our synthetic backup, not HA's
        # real device records. This tests the exact backed-up bytes.
        shutil.copy2(backups[0], self.dest)
        self.assertEqual(self.dest.read_bytes(), old)
        self.assert_no_config_migration()
        self.assertEqual(backups[0].read_bytes(), old)

    def test_user_modified_managed_dp_map_is_preserved(self):
        self.assertEqual(self.installer.sync_managed_template(self.config), "installed")
        modified = self.fresh.replace(
            b"humidifier_mode_dp: '24'", b"humidifier_mode_dp: '999'"
        )
        self.assertNotEqual(modified, self.fresh)
        self.dest.write_bytes(modified)
        self.assertIn(
            "locally modified template preserved",
            self.installer.sync_managed_template(self.config),
        )
        self.assertEqual(self.dest.read_bytes(), modified)
        self.assertFalse(list(self.localtuya_dir.glob("*.bak")))
        self.assert_no_config_migration()

    def test_untracked_custom_name_and_dp_never_overwritten(self):
        custom = self.fresh.replace(b"friendly_name: Temperature", b"friendly_name: My Temperature")
        custom = custom.replace(b"id: '10'", b"id: '999'")
        self.dest.write_bytes(custom)
        self.assertIn("preserved", self.installer.sync_managed_template(self.config))
        self.assertEqual(self.dest.read_bytes(), custom)
        self.assertFalse(self.marker.exists())
        self.assert_no_config_migration()

    def test_legacy_official_units_upgrade_does_not_migrate_entities(self):
        old = self.fresh.replace(b"unit_of_measurement: \xce\xbcg/m\xc2\xb3", b"unit_of_measurement: ug/m3")
        old = old.replace(b"unit_of_measurement: d", b"unit_of_measurement: days")
        self.assertTrue(self.installer._only_known_legacy_differences(old, self.fresh))
        self.dest.write_bytes(old)
        self.assertIn("updated", self.installer.sync_managed_template(self.config))
        self.assertEqual(self.dest.read_bytes(), self.fresh)
        self.assertEqual(len(list(self.localtuya_dir.glob("*.bak"))), 1)
        self.assert_no_config_migration()

    def test_unrecognized_legacy_dp_edit_skips_update(self):
        old = self.fresh.replace(b"humidifier_set_humidity_dp: '13'",
                                  b"humidifier_set_humidity_dp: '900'")
        old = old.replace(b"unit_of_measurement: d", b"unit_of_measurement: days")
        self.assertFalse(self.installer._only_known_legacy_differences(old, self.fresh))
        self.dest.write_bytes(old)
        self.assertIn("preserved", self.installer.sync_managed_template(self.config))
        self.assertEqual(self.dest.read_bytes(), old)
        self.assert_no_config_migration()

    def test_missing_localtuya_returns_safe_skip(self):
        shutil.rmtree(self.config / "custom_components/localtuya")
        self.assertIn("not installed", self.installer.sync_managed_template(self.config))
        self.assert_no_config_migration()

    def test_template_symlink_not_followed(self):
        outside = self.config / "outside.yaml"
        outside.write_text("external fixture sentinel")
        self.dest.symlink_to(outside)
        self.assertIn("symlink", self.installer.sync_managed_template(self.config))
        self.assertEqual(outside.read_text(), "external fixture sentinel")
        self.assert_no_config_migration()

    def test_symlinked_localtuya_directory_is_refused(self):
        outside = self.config / "external-template-dir"
        outside.mkdir()
        shutil.rmtree(self.config / "custom_components/localtuya")
        (self.config / "custom_components/localtuya").symlink_to(outside, target_is_directory=True)
        (outside / "templates").mkdir()
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.sync_managed_template(self.config)
        self.assertFalse((outside / "templates/venta_aw730.yaml").exists())
        self.assert_no_config_migration()

    def test_symlinked_templates_directory_is_refused(self):
        outside = self.config / "external-templates"
        outside.mkdir()
        self.localtuya_dir.rmdir()
        self.localtuya_dir.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.sync_managed_template(self.config)
        self.assertFalse((outside / "venta_aw730.yaml").exists())
        self.assert_no_config_migration()

    def test_symlinked_tracking_marker_is_refused_before_update(self):
        old = self.fresh.replace(b"friendly_name: Temperature", b"friendly_name: Old Temperature")
        self.dest.write_bytes(old)
        outside = self.config / "external-marker"
        outside.write_text("marker sentinel")
        self.marker.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.sync_managed_template(self.config)
        self.assertEqual(self.dest.read_bytes(), old)
        self.assertEqual(outside.read_text(), "marker sentinel")
        self.assert_no_config_migration()

    def test_symlinked_storage_directory_is_refused_before_install(self):
        sentinel_dir = self.config / "another-storage"
        sentinel_dir.mkdir()
        # Preserve synthetic fixture paths by moving their parent directory
        # and returning the logical original via a symlink.
        real_storage = self.config / ".storage"
        moved = self.config / "real-storage"
        real_storage.rename(moved)
        real_storage.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.sync_managed_template(self.config)
        self.assertFalse(self.dest.exists())
        self.assert_no_config_migration()

    def test_backup_collision_never_overwrites_existing_backup(self):
        self.dest.write_bytes(b"old managed fixture")
        fixed = datetime(2026, 11, 22, 13, 0, 0, tzinfo=timezone.utc)
        backup = self.localtuya_dir / "venta_aw730.yaml.20261122T130000Z.bak"
        backup.write_bytes(b"preexisting backup")
        clock = SimpleNamespace(now=lambda _tz: fixed)
        with patch.object(self.installer, "datetime", clock):
            with self.assertRaisesRegex(RuntimeError, "Backup already exists"):
                self.installer.install(self.config, replace=True)
        self.assertEqual(backup.read_bytes(), b"preexisting backup")
        self.assertEqual(self.dest.read_bytes(), b"old managed fixture")
        self.assert_no_config_migration()

    def test_corrupt_marker_does_not_authorize_template_replacement(self):
        self.marker.write_text('{"destination_sha256":"invalid"}')
        custom = self.fresh.replace(b"friendly_name: Temperature", b"friendly_name: Custom")
        self.dest.write_bytes(custom)
        self.assertIn("preserved", self.installer.sync_managed_template(self.config))
        self.assertEqual(self.dest.read_bytes(), custom)
        self.assert_no_config_migration()


if __name__ == "__main__":
    unittest.main()
