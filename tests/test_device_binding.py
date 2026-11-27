"""P06 source identity tests; synthetic registry only, no HA or hardware."""
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

PATH = Path(__file__).resolve().parents[1] / "custom_components/venta_homekit_native/device_binding.py"
SPEC = importlib.util.spec_from_file_location("venta_device_binding_test", PATH)
assert SPEC and SPEC.loader
binding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding)


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.source = NS(platform="localtuya", entity_id="humidifier.fixture",
                         config_entry_id="fixture-config", device_id="fixture-device",
                         unique_id="fixture-entity", disabled_by=None, hidden_by=None)
        self.device = NS(id="fixture-device", config_entry_id="fixture-config", disabled_by=None)
        self.entry = NS(entry_id="fixture-config", domain="localtuya", disabled_by=None)

    def identity(self):
        return binding.source_identity(self.source, self.device, self.entry)

    def test_stable_across_entity_rename_and_restart(self):
        before = self.identity()
        self.source.entity_id = "humidifier.renamed"
        self.assertEqual(before, self.identity())
        self.assertEqual(before, binding.source_identity(
            NS(**vars(self.source)), NS(**vars(self.device)), NS(**vars(self.entry))))

    def test_replacement_changes_identity(self):
        before = self.identity()
        self.source.unique_id = "replacement"
        self.assertNotEqual(before, self.identity())

    def test_separate_device_info_no_raw_identifiers_or_connections(self):
        result = binding.logical_device_info(self.identity())
        self.assertEqual(result["manufacturer"], "Venta")
        self.assertEqual(result["model"], "AW730")
        self.assertEqual(len(result["identifiers"]), 1)
        self.assertEqual(next(iter(result["identifiers"]))[0], binding.DOMAIN)
        self.assertNotIn("connections", result)
        self.assertNotIn("via_device", result)
        self.assertNotIn("fixture-", repr(result))

    def test_wrong_device_or_owner_rejected(self):
        for obj, key, value in (
            (self.device, "id", "other-device"),
            (self.device, "config_entry_id", "other-config"),
            (self.entry, "entry_id", "other-config"),
        ):
            with self.subTest(key=key):
                old = getattr(obj, key)
                setattr(obj, key, value)
                with self.assertRaisesRegex(binding.BindingError, "source_ownership_changed"):
                    self.identity()
                setattr(obj, key, old)

    def test_no_other_platform_or_wrong_entity_domain(self):
        for obj, key, value in (
            (self.source, "platform", "mqtt"),
            (self.source, "entity_id", "switch.fixture"),
            (self.entry, "domain", "mqtt"),
        ):
            with self.subTest(key=key):
                old = getattr(obj, key)
                setattr(obj, key, value)
                with self.assertRaisesRegex(binding.BindingError, "wrong_source"):
                    self.identity()
                setattr(obj, key, old)

    def test_disabled_or_hidden_source_is_rejected(self):
        for obj, key in (
            (self.source, "disabled_by"), (self.source, "hidden_by"),
            (self.device, "disabled_by"), (self.entry, "disabled_by"),
        ):
            with self.subTest(key=key):
                setattr(obj, key, "user")
                with self.assertRaisesRegex(binding.BindingError, "source_disabled"):
                    self.identity()
                setattr(obj, key, None)

    def test_missing_identity_rejected(self):
        self.source.unique_id = None
        with self.assertRaisesRegex(binding.BindingError, "source_identity_missing"):
            self.identity()
        with self.assertRaisesRegex(binding.BindingError, "source_missing"):
            binding.source_identity(None, self.device, self.entry)

    def test_invalid_logical_id_rejected(self):
        for value in ("", "z" * 64, "0" * 63, None):
            with self.subTest(value=value), self.assertRaises(binding.BindingError):
                binding.logical_device_info(value)


if __name__ == "__main__":
    unittest.main()
