"""Synthetic-only regressions for the private HomeKit restore audit."""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts.ha_private_restore_audit import audit, required_paths


def _tar_bytes(members: dict[str, bytes], mode: str = "w:gz") -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode=mode) as stream:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o600
            stream.addfile(info, io.BytesIO(content))
    return output.getvalue()


class PrivateRestoreAuditTests(unittest.TestCase):
    BRIDGE = "fake-ci-bridge"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.live = self.root / "live"
        self.live.mkdir()
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.backup = self.root / "fake-backup.tar"
        self.files = {
            "configuration.yaml": b"homeassistant:\n  name: Fake\n",
            ".storage/core.config_entries": json.dumps({
                "data": {"entries": [{"domain": "homekit", "entry_id": self.BRIDGE}]},
            }).encode(),
            f".storage/homekit.{self.BRIDGE}.aids": b'{"data":{}}',
            f".storage/homekit.{self.BRIDGE}.iids": b'{"data":{}}',
            f".storage/homekit.{self.BRIDGE}.state": json.dumps({
                "private_key": "synthetic-only",
                "public_key": "synthetic-only",
                "paired_clients": {"ci-fake": {}},
            }).encode(),
            "custom_components/venta_homekit_native/manifest.json": b'{"domain":"venta_homekit_native","version":"1.0.4"}',
        }
        for name, body in self.files.items():
            p = self.live / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        self.write_backup()

    def write_backup(self, files=None, *, manifest=None):
        compressed = _tar_bytes({
            "data/" + k: v for k, v in (self.files if files is None else files).items()
        })
        self.backup.write_bytes(_tar_bytes({
            "./backup.json": json.dumps(
                {"homeassistant": {"version": "2026.11.1"}}
                if manifest is None else manifest
            ).encode(),
            "homeassistant.tar.gz": compressed,
        }, mode="w:"))

    def run_audit(self):
        return audit(
            self.backup, self.live, self.BRIDGE,
            scratch_root=self.scratch,
        )

    def test_all_six_real_files_restored_byte_identically(self):
        receipt = self.run_audit()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["restored_in_private_scratch"], 6)
        self.assertEqual(receipt["homekit_paired_client_count"], 1)
        self.assertTrue(receipt["byte_identical_to_live"])
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(
            (self.live / "configuration.yaml").read_bytes(),
            self.files["configuration.yaml"],
        )

    def test_missing_member_fails_closed(self):
        a = dict(self.files)
        del a["configuration.yaml"]
        self.write_backup(a)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_changed_yaml_fails_closed(self):
        (self.live / "configuration.yaml").write_bytes(b"homeassistant: modified\n")
        with self.assertRaises(AssertionError):
            self.run_audit()
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_changed_homekit_keys_fail_closed(self):
        p = self.live / f".storage/homekit.{self.BRIDGE}.state"
        value = json.loads(p.read_text())
        value["private_key"] = "different-synthetic-key"
        p.write_text(json.dumps(value))
        with self.assertRaises(AssertionError):
            self.run_audit()

    def test_nonpairing_backup_is_rejected(self):
        a = dict(self.files)
        p = f".storage/homekit.{self.BRIDGE}.state"
        a[p] = b'{"private_key":"x","public_key":"y","paired_clients":{}}'
        self.write_backup(a)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_backup_symlink_rejected(self):
        other = self.root / "actual.tar"
        self.backup.rename(other)
        self.backup.symlink_to(other)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_live_symlink_rejected(self):
        p = self.live / "configuration.yaml"
        other = self.root / "outside.yaml"
        other.write_bytes(self.files["configuration.yaml"])
        p.unlink()
        p.symlink_to(other)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_missing_manifest_rejected(self):
        self.write_backup(manifest={"type": "partial"})
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_modified_integration_domain_rejected(self):
        p = self.live / "custom_components/venta_homekit_native/manifest.json"
        p.write_bytes(b'{"domain":"other"}')
        with self.assertRaises(AssertionError):
            self.run_audit()
        a = dict(self.files)
        a["custom_components/venta_homekit_native/manifest.json"] = b'{"domain":"other"}'
        self.write_backup(a)
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_invalid_bridge_identifier_rejected(self):
        for name in ("../etc", "bad/name", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                required_paths(name)

    def test_scratch_inside_live_is_rejected(self):
        inside = self.live / "scratch"
        inside.mkdir()
        with self.assertRaises(ValueError):
            audit(self.backup, self.live, self.BRIDGE, scratch_root=inside)

    def test_transient_files_are_destroyed_after_mismatch(self):
        self.live.joinpath("configuration.yaml").write_bytes(b"changed")
        with self.assertRaises(AssertionError):
            self.run_audit()
        self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
