"""Synthetic guarded release transactions: no Docker or owner data."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts import ha_release_transaction as rel


class VentaReleaseTransactionTests(unittest.TestCase):
    BRIDGE = "ci-homekit-bridge"
    ENTITY = "humidifier.fixture_venta"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "ha"
        self.ledger = self.base / "release-ledger"
        self.scratch = self.base / "ram"
        self.scratch.mkdir()
        self.source = self.base / "source"
        self.component = self.root / "custom_components/venta_homekit_native"
        self.component.mkdir(parents=True)
        new = self.source / "custom_components/venta_homekit_native"
        new.mkdir(parents=True)
        (new / "templates").mkdir()
        (new / "manifest.json").write_text(
            json.dumps({"domain": rel.DOMAIN, "version": rel.NEW}),
            encoding="utf-8",
        )
        (new / "__init__.py").write_text("VERSION = '1.2.0'\n")
        (new / "services.yaml").write_text("reload_venta:\n")
        (new / "install_localtuya_template.py").write_text("pass\n")
        (new / "templates/venta_aw730.yaml").write_text("name: fixture\n")
        (self.source / "VERSION").write_text(rel.NEW + "\n")
        (self.component / "manifest.json").write_text(
            json.dumps({"domain": rel.DOMAIN, "version": rel.EXPECTED_OLD}),
            encoding="utf-8",
        )
        (self.component / "__init__.py").write_text("ORIGINAL_INSTALL\n")
        (self.component / "user-custom.conf").write_text("custom content\n")
        (self.root / ".storage").mkdir()
        (self.root / "configuration.yaml").write_text(
            f"venta_homekit_native:\n  humidifier_entity: {self.ENTITY}\n",
            encoding="utf-8",
        )
        entries = {
            "data": {"entries": [{
                "domain": "homekit",
                "entry_id": self.BRIDGE,
                "options": {
                    "mode": "bridge", "filter": {"include_entities": [self.ENTITY]},
                },
            }]}
        }
        (self.root / ".storage/core.config_entries").write_text(json.dumps(entries))
        self.files = {
            f".storage/homekit.{self.BRIDGE}.aids": b'{"data":{"aids":{}}}',
            f".storage/homekit.{self.BRIDGE}.iids": b'{"data":{"iids":{}}}',
            f".storage/homekit.{self.BRIDGE}.state":
                b'{"private_key":"fixture","public_key":"fixture","paired_clients":{"fixture":{}},"config_version":1}',
        }
        for name, body in self.files.items():
            (self.root / name).write_bytes(body)

    def stage(self):
        with patch.object(rel, "verify_baseline", return_value=(
            self.BRIDGE, self.root / "backups/fake.tar"
        )):
            return rel.stage(self.source, self.root, self.ledger, self.scratch)

    def install(self):
        return rel.install(self.root, self.ledger)

    def test_source_version_and_existing_bridge_are_exact(self):
        self.assertEqual(rel.source_version(self.source), rel.NEW)
        self.assertEqual(rel.select_bridge(self.root), self.BRIDGE)

    def test_full_install_verify_and_rollback_no_live_ha(self):
        self.assertEqual(self.stage()["stage"], "READY")
        self.assertEqual(rel.manifest_version(self.component / "manifest.json"),
                         rel.EXPECTED_OLD)
        self.assertEqual(self.install()["stage"], "INSTALLED_NEEDS_RESTART")
        self.assertEqual(rel.manifest_version(self.component / "manifest.json"),
                         rel.NEW)
        self.assertEqual(
            rel.verify(self.root, self.ledger, check_health=False)["status"],
            "PRODUCTION_VERIFY_PASS",
        )
        self.assertEqual(
            rel.rollback(self.root, self.ledger, restore_storage=False)["status"],
            "ROLLBACK_FILES_RESTORED",
        )
        self.assertEqual(
            rel.verify_rollback(self.root, self.ledger, check_health=False)["status"],
            "ROLLBACK_VERIFIED",
        )
        self.assertEqual((self.component / "user-custom.conf").read_text(),
                         "custom content\n")
        self.assertEqual((self.component / "__init__.py").read_text(),
                         "ORIGINAL_INSTALL\n")

    def test_staging_never_modifies_old_component_or_yaml(self):
        old = (self.component / "manifest.json").read_bytes()
        yaml = (self.root / "configuration.yaml").read_bytes()
        self.stage()
        self.assertEqual((self.component / "manifest.json").read_bytes(), old)
        self.assertEqual((self.root / "configuration.yaml").read_bytes(), yaml)
        self.assertEqual(rel.receipt(
            rel.paths(self.root, self.ledger, rel.NEW)["meta"]
        )["status"], "STAGED")

    def test_invalid_new_manifest_prevents_preflight(self):
        p = self.source / "custom_components/venta_homekit_native/manifest.json"
        p.write_text('{"domain":"venta_homekit_native","version":"1.0.4"}')
        with self.assertRaises(ValueError):
            rel.source_version(self.source)
        self.assertFalse(self.ledger.exists())

    def test_modified_source_version_refuses_preflight(self):
        (self.source / "VERSION").write_text("1.0.4\n")
        with self.assertRaises(ValueError):
            rel.source_version(self.source)

    def test_no_automatic_duplicate_release_attempt(self):
        self.stage()
        with self.assertRaises(ValueError):
            self.stage()

    def test_repeated_install_is_not_silently_idempotent(self):
        self.stage()
        self.install()
        with self.assertRaises(ValueError):
            self.install()

    def test_change_of_old_install_after_stage_blocks_apply(self):
        self.stage()
        original = self.component / "manifest.json"
        original.write_text(
            '{"domain":"venta_homekit_native","version":"1.0.4","note":"new"}'
        )
        with self.assertRaises(ValueError):
            self.install()

    def test_changed_legacy_yaml_is_detected_by_verify(self):
        self.stage()
        self.install()
        (self.root / "configuration.yaml").write_bytes(
            b"venta_homekit_native: changed\n"
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_homekit_iids_changed_is_detected_by_verify(self):
        self.stage()
        self.install()
        (self.root / f".storage/homekit.{self.BRIDGE}.iids").write_text(
            '{"data":{"iids":{"changed":true}}}'
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_postboot_metadata_changes_do_not_trigger_rollback(self):
        entry_file = self.root / ".storage/core.config_entries"
        original = json.loads(entry_file.read_text())
        original["data"]["entries"].append({
            "entry_id": "unrelated_intents_entry", "domain": "yandex_station_intents",
            "data": {"revision": 1}, "modified_at": "before",
        })
        entry_file.write_text(json.dumps(original))
        self.stage()
        self.install()
        current = json.loads(entry_file.read_text())
        current["data"]["entries"][-1]["data"] = {"revision": 2}
        current["data"]["entries"][-1]["modified_at"] = "after"
        entry_file.write_text(json.dumps(current))
        state_file = self.root / f".storage/homekit.{self.BRIDGE}.state"
        state = json.loads(state_file.read_text())
        state["config_version"] += 1
        state_file.write_text(json.dumps(state))
        for _ in range(2):
            self.assertEqual(rel.verify(self.root, self.ledger, check_health=False)["status"],
                             "PRODUCTION_VERIFY_PASS")

    def test_homekit_pairing_change_still_fails_verify(self):
        self.stage()
        self.install()
        state_file = self.root / f".storage/homekit.{self.BRIDGE}.state"
        value = json.loads(state_file.read_text())
        value["paired_clients"]["intruder"] = {}
        state_file.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_decreasing_homekit_config_version_fails_verify(self):
        self.stage()
        self.install()
        state_file = self.root / f".storage/homekit.{self.BRIDGE}.state"
        value = json.loads(state_file.read_text())
        value["config_version"] = 0
        state_file.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_homekit_bridge_config_entry_change_fails_verify(self):
        self.stage()
        self.install()
        path = self.root / ".storage/core.config_entries"
        value = json.loads(path.read_text())
        value["data"]["entries"][0]["options"]["filter"]["include_entities"] = []
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_duplicate_entry_id_fails_verify_even_if_unrelated(self):
        self.stage()
        self.install()
        path = self.root / ".storage/core.config_entries"
        value = json.loads(path.read_text())
        other = dict(value["data"]["entries"][0])
        other["domain"] = "unrelated"
        value["data"]["entries"].append(other)
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
            rel.verify(self.root, self.ledger, check_health=False)

    def test_rollback_after_live_update_stops_ha_then_restores_pairing(self):
        self.stage()
        self.install()
        state = self.root / f".storage/homekit.{self.BRIDGE}.state"
        state.write_bytes(b"changed")
        with patch.object(rel.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout="true"),
            SimpleNamespace(returncode=0),
        ]) as docker:
            rel.rollback(self.root, self.ledger)
        self.assertEqual(docker.call_count, 2)
        self.assertEqual(state.read_bytes(), self.files[
            f".storage/homekit.{self.BRIDGE}.state"
        ])
        self.assertEqual(
            rel.verify_rollback(self.root, self.ledger, check_health=False)["status"],
            "ROLLBACK_VERIFIED",
        )

    def test_rollback_preserves_unrelated_ha_changes_and_hap_revision(self):
        self.stage()
        self.install()
        entry_file = self.root / ".storage/core.config_entries"
        contents = json.loads(entry_file.read_text())
        contents["data"]["entries"].append({
            "domain": "unrelated", "entry_id": "keep-new-integration",
            "data": {"new_setting": True},
        })
        entry_file.write_text(json.dumps(contents))
        state_file = self.root / f".storage/homekit.{self.BRIDGE}.state"
        state = json.loads(state_file.read_text())
        state["config_version"] += 1
        state_file.write_text(json.dumps(state))
        with patch.object(rel.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout="true"),
            SimpleNamespace(returncode=0),
        ]):
            self.assertEqual(
                rel.rollback(self.root, self.ledger)["status"],
                "ROLLBACK_FILES_RESTORED",
            )
        remaining = json.loads(entry_file.read_text())
        self.assertEqual(len(remaining["data"]["entries"]), 2)
        self.assertEqual(json.loads(state_file.read_text())["config_version"], 2)
        self.assertEqual(
            rel.verify_rollback(self.root, self.ledger, check_health=False)["status"],
            "ROLLBACK_VERIFIED",
        )

    def test_missing_config_entries_is_restored_during_rollback(self):
        self.stage()
        self.install()
        config = self.root / ".storage/core.config_entries"
        config.unlink()
        with patch.object(rel.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout="true"),
            SimpleNamespace(returncode=0),
        ]):
            rel.rollback(self.root, self.ledger)
        self.assertEqual(
            rel.verify_rollback(self.root, self.ledger, check_health=False)["status"],
            "ROLLBACK_VERIFIED",
        )

    def test_pre_install_failure_does_not_stop_homeassistant(self):
        self.stage()
        original = (self.root / "configuration.yaml").read_bytes()
        with patch.object(rel.subprocess, "run") as docker:
            rel.rollback(self.root, self.ledger)
        docker.assert_not_called()
        self.assertEqual(
            (self.root / "configuration.yaml").read_bytes(), original
        )

    def test_crash_between_atomic_directory_moves_restores_previous(self):
        self.stage()
        real_replace = os.replace
        count = [0]

        def fail_second(src, dest):
            count[0] += 1
            if count[0] == 2:
                raise OSError("simulated power cut")
            return real_replace(src, dest)

        with patch.object(rel.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.install()
        with patch.object(rel.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout="true"),
            SimpleNamespace(returncode=0),
        ]):
            rel.rollback(self.root, self.ledger)
        self.assertEqual(rel.manifest_version(self.component / "manifest.json"),
                         rel.EXPECTED_OLD)

    def test_restored_homekit_material_is_checksum_checked(self):
        self.stage()
        self.install()
        path = rel.paths(self.root, self.ledger, rel.NEW)["guard"]
        (path / "configuration.yaml").write_text("tampered")
        with patch.object(rel.subprocess, "run") as docker:
            with self.assertRaises(ValueError):
                rel.rollback(self.root, self.ledger)
        docker.assert_not_called()

    def test_homekit_bridge_ambiguity_refused(self):
        p = self.root / ".storage/core.config_entries"
        data = json.loads(p.read_text())
        extra = dict(data["data"]["entries"][0])
        extra["entry_id"] = "another-homekit-bridge"
        data["data"]["entries"].append(extra)
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            rel.select_bridge(self.root)

    def test_no_humidifier_in_legacy_yaml_refused(self):
        (self.root / "configuration.yaml").write_text(
            "venta_homekit_native:\n  humidifier_entity: humidifier.other\n"
        )
        with self.assertRaises(ValueError):
            rel.select_bridge(self.root)

    def test_symlinked_component_input_refused(self):
        p = self.source / "custom_components/venta_homekit_native/secret.py"
        target = self.root / "configuration.yaml"
        p.symlink_to(target)
        with self.assertRaises(ValueError):
            rel.source_version(self.source)

    def test_recipe_includes_rollback_and_bounded_verify(self):
        recipe = json.loads((Path(__file__).resolve().parents[1] /
                             ".mcpshka/release.json").read_text())
        self.assertEqual(recipe["schema"], "mcpshka.release/v1")
        self.assertEqual(recipe["version_file"], "VERSION")
        self.assertEqual(recipe["rollback_from"], "install")
        self.assertEqual(recipe["rollback"]["name"], "restore")
        names = [item["name"] for item in recipe["steps"]]
        self.assertEqual(names, ["preflight", "stage", "install", "restart",
                                 "verify"])
        self.assertIn("IDENTITY_DRIFT", recipe["steps"][-1]["fail"])


    def test_rollback_after_container_already_stopped_does_not_stop_again(self):
        self.stage()
        self.install()
        with patch.object(rel.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="false"
        )) as docker:
            result = rel.rollback(self.root, self.ledger)
        self.assertEqual(result["status"], "ROLLBACK_FILES_RESTORED")
        docker.assert_called_once()
        self.assertEqual(docker.call_args.args[0][1], "inspect")


if __name__ == "__main__":
    unittest.main()
