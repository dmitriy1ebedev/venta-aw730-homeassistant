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


class RegistryRegistrationTests(unittest.TestCase):
    def setUp(self):
        import sys
        import types
        from unittest.mock import Mock, patch

        self.entry = NS(domain=binding.DOMAIN, entry_id="venta-ci", disabled_by=None, data={})
        self.source_entry = NS(domain="localtuya", entry_id="source-ci", disabled_by=None)
        self.source = NS(platform="localtuya", entity_id="humidifier.fixture", unique_id="source-entity",
                         config_entry_id="source-ci", device_id="source-device",
                         disabled_by=None, hidden_by=None)
        self.source_device = NS(id="source-device", config_entry_id="source-ci", disabled_by=None)
        self.card = None
        self.registry = NS(
            async_get=Mock(return_value=self.source_device),
            async_get_device_by_identifier=Mock(side_effect=lambda identifier, owner:
                self.card if self.card and identifier in self.card.identifiers else None),
            async_get_or_create=Mock(side_effect=self.create),
        )
        self.lookup = Mock(return_value=self.source)
        self.owner_lookup = Mock(side_effect=lambda key:
            {"source-ci": self.source_entry, "venta-ci": self.entry}.get(key))
        self.update = Mock(side_effect=lambda entry, data: setattr(entry, "data", data))
        self.hass = NS(config_entries=NS(async_get_entry=self.owner_lookup,
                                        async_update_entry=self.update))
        homeassistant = types.ModuleType("homeassistant")
        helpers = types.ModuleType("homeassistant.helpers")
        dr = types.ModuleType("homeassistant.helpers.device_registry")
        er = types.ModuleType("homeassistant.helpers.entity_registry")
        dr.async_get = lambda _hass: self.registry
        dr.async_entries_for_config_entry = lambda _registry, _entry_id: [self.card] if self.card else []
        er.async_get = lambda _hass: NS(async_get=self.lookup)
        helpers.device_registry, helpers.entity_registry = dr, er
        homeassistant.helpers = helpers
        self.modules = patch.dict(sys.modules, {"homeassistant": homeassistant,
            "homeassistant.helpers": helpers, "homeassistant.helpers.device_registry": dr,
            "homeassistant.helpers.entity_registry": er})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def create(self, *, config_entry_id, identifiers, **kwargs):
        self.assertEqual(config_entry_id, self.entry.entry_id)
        if self.card is None:
            self.card = NS(id="logical-venta", config_entry_id=config_entry_id,
                           identifiers=identifiers, connections=set(), **kwargs)
        return self.card

    def register(self):
        return binding.register_logical_device(self.hass, self.entry, self.source.entity_id)

    def test_registration_pins_source_and_does_not_duplicate(self):
        result = self.register()
        self.assertEqual(result[1], "logical-venta")
        self.assertEqual(self.entry.data[binding.PIN_FIELD], result[0])
        self.assertEqual(self.register(), result)
        self.update.assert_called_once()
        self.assertEqual(self.source.device_id, "source-device")
        self.assertEqual(self.source_device.config_entry_id, "source-ci")

    def test_replacement_is_rejected_even_when_card_missing(self):
        self.register()
        self.card = None
        self.source.unique_id = "replacement"
        with self.assertRaisesRegex(binding.BindingError, "source_identity_changed"):
            self.register()
        self.assertIsNone(self.card)
        self.registry.async_get_or_create.assert_called_once()

    def test_missing_source_no_registration_or_pin(self):
        self.lookup.return_value = None
        with self.assertRaisesRegex(binding.BindingError, "source_missing"):
            self.register()
        self.registry.async_get_or_create.assert_not_called()
        self.update.assert_not_called()

    def test_wrong_entry_and_foreign_owned_device_rejected(self):
        self.entry.domain = "mqtt"
        with self.assertRaisesRegex(binding.BindingError, "invalid_venta_entry"):
            self.register()
        self.entry.domain = binding.DOMAIN
        self.card = NS(id="other", identifiers={("foreign", "existing")}, connections=set())
        with self.assertRaisesRegex(binding.BindingError, "logical_device_conflict"):
            self.register()
        self.registry.async_get_or_create.assert_not_called()
        self.update.assert_not_called()

    def test_corrupt_persisted_pin_cannot_be_overwritten(self):
        self.entry.data[binding.PIN_FIELD] = "invalid"
        with self.assertRaisesRegex(binding.BindingError, "invalid_logical_identity"):
            self.register()
        self.registry.async_get_or_create.assert_not_called()
        self.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
