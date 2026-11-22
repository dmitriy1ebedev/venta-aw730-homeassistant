"""Isolated release 1.0.5 file-level upgrade and rollback.

This uses generated config entries and HomeKit identity markers only. It does
NOT restart Home Assistant or verify survival of a real paired HomeKit bridge.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_release import COMPONENT, build_archive
from scripts.stage_ha_runtime import stage


def _file_hashes(component: Path) -> dict[str, str]:
    return {
        f.relative_to(component).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(component.rglob("*"))
        if f.is_file()
    }


def _sync(config: Path) -> str:
    script = config / COMPONENT / "install_localtuya_template.py"
    spec = importlib.util.spec_from_file_location("venta_105_rollback_helper", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sync_managed_template(config)


class IsolatedRollbackContracts(unittest.TestCase):
    def test_upgrade_and_restore_keep_existing_ids_and_user_template(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive = base / "candidate.zip"
            artifact = build_archive(archive, expected_tag="v1.0.5")
            self.assertEqual(artifact["version"], "1.0.5")
            stage(archive, base / "candidate")
            config = base / "fake-ha"
            shutil.copytree(base / "candidate", config)
            component = config / COMPONENT

            # This branch differs from the 1.0.4 runtime only by its
            # manifest version. Simulate an installed 1.0.4 baseline.
            manifest_path = component / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["version"] = "1.0.4"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
            old_hashes = _file_hashes(component)
            backup = base / "backup-of-installed-component"
            shutil.copytree(component, backup)

            storage = config / ".storage"
            storage.mkdir()
            entries = storage / "core.config_entries"
            registry = storage / "core.entity_registry"
            pairing = storage / "homekit.synthetic-identity"
            entries.write_bytes(b'{"data":{"entries":[{"entry_id":"preserve-ci-entry"}]}}\n')
            registry.write_bytes(b'{"data":{"entities":[{"unique_id":"preserve-ci-id"}]}}\n')
            pairing.write_bytes(b'{"accessory_id":"preserve-ci-homekit-id"}\n')
            observed = {p.name: p.read_bytes() for p in (entries, registry, pairing)}

            localtuya = config / "custom_components/localtuya/templates"
            localtuya.mkdir(parents=True)
            user_template = localtuya / "venta_aw730.yaml"
            user_template.write_bytes(b"private user template fixture -- preserve me\n")

            # Upgrade only the component package. No config-entry migration,
            # no force-reset of a custom LocalTuya template or pairing.
            shutil.rmtree(component)
            shutil.copytree(base / "candidate" / COMPONENT, component)
            self.assertEqual(json.loads(manifest_path.read_text())["version"], "1.0.5")
            self.assertIn("preserved", _sync(config))
            self.assertEqual(user_template.read_bytes(),
                             b"private user template fixture -- preserve me\n")
            for p in (entries, registry, pairing):
                self.assertEqual(p.read_bytes(), observed[p.name])

            # Byte-identical rollback of the backed-up component; HA itself
            # is not started, and no real pairings are recreated.
            shutil.rmtree(component)
            shutil.copytree(backup, component)
            self.assertEqual(_file_hashes(component), old_hashes)
            self.assertEqual(json.loads(manifest_path.read_text())["version"], "1.0.4")
            self.assertIn("preserved", _sync(config))
            for p in (entries, registry, pairing):
                self.assertEqual(p.read_bytes(), observed[p.name])
            self.assertEqual(user_template.read_bytes(),
                             b"private user template fixture -- preserve me\n")


if __name__ == "__main__":
    unittest.main()
