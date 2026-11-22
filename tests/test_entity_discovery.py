"""P03.2: prevent accidental associations across LocalTuya devices.

The real source module is imported directly, without starting HA or talking to
any physical device. Registry entries are synthetic and contain no secrets.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components/venta_homekit_native/entity_discovery.py"
SPEC = importlib.util.spec_from_file_location("venta_entity_discovery_test", PATH)
assert SPEC and SPEC.loader
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


def entity(
    entity_id: str,
    *,
    device: str = "fake-device-a",
    config: str = "fake-localtuya-configuration",
    platform: str = "localtuya",
    device_class: str | None = None,
    original_class: str | None = None,
    disabled: str | None = None,
    hidden: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id, device_id=device,
        config_entry_id=config, platform=platform,
        device_class=device_class, original_device_class=original_class,
        disabled_by=disabled, hidden_by=hidden,
    )


class SafeRegistryChoiceTests(unittest.TestCase):
    def setUp(self):
        self.humidifier = entity("humidifier.venta_fixture")
        self.entries = [
            self.humidifier,
            entity("select.venta_fan"),
            entity("select.venta_brightness"),
            entity("switch.venta_led"),
            entity("sensor.venta_temperature", device_class="temperature"),
            entity("sensor.venta_humidity", device_class="humidity"),
        ]
        self.selected = {
            "fan": "select.venta_fan",
            "led": "switch.venta_led",
            "brightness": "select.venta_brightness",
            "temperature": "sensor.venta_temperature",
            "humidity": "sensor.venta_humidity",
        }

    def plan(self):
        return discovery.plan_from_entries(self.humidifier, self.entries)

    def validate(self, selections=None, **kwargs):
        return discovery.validate_selection(
            self.humidifier, self.entries,
            self.selected if selections is None else selections, **kwargs
        )

    def test_all_five_roles_are_visible_but_never_automatically_applied(self):
        p = self.plan()
        self.assertEqual(p["status"], "review_required")
        self.assertTrue(p["can_submit"])
        self.assertTrue(p["read_only"])
        self.assertEqual(set(p["roles"]), set(discovery.ROLES))
        self.assertTrue(all(v["requires_confirmation"] for v in p["roles"].values()))
        self.assertIsNone(p["roles"]["fan"]["suggested"])
        self.assertIsNone(p["roles"]["brightness"]["suggested"])
        self.assertEqual(p["roles"]["led"]["suggested"], "switch.venta_led")
        self.assertEqual(p["roles"]["temperature"]["suggested"], "sensor.venta_temperature")
        self.assertEqual(p["roles"]["humidity"]["suggested"], "sensor.venta_humidity")

    def test_explicit_valid_mapping(self):
        self.assertEqual(self.validate(), {})
        self.assertEqual(self.selected["fan"], "select.venta_fan")

    def test_same_config_entry_but_other_device_is_never_offered(self):
        self.entries += [
            entity("select.other_fan", device="fake-device-b"),
            entity("switch.other_led", device="fake-device-b"),
            entity("sensor.other_temperature", device="fake-device-b", device_class="temperature"),
            entity("sensor.other_humidity", device="fake-device-b", device_class="humidity"),
        ]
        p = self.plan()
        for role in discovery.ROLES:
            self.assertTrue(all(".other_" not in option for option in p["roles"][role]["options"]))
        for role, other in (
            ("fan", "select.other_fan"),
            ("led", "switch.other_led"),
            ("temperature", "sensor.other_temperature"),
            ("humidity", "sensor.other_humidity"),
        ):
            mapping = dict(self.selected, **{role: other})
            with self.subTest(role=role):
                self.assertEqual(self.validate(mapping)[role], "different_or_disabled_device")

    def test_same_device_with_other_localtuya_config_entry_is_rejected(self):
        self.entries += [entity("switch.rogue_led", config="fake-other-configuration")]
        self.assertNotIn("switch.rogue_led", self.plan()["roles"]["led"]["options"])
        self.assertEqual(
            self.validate(dict(self.selected, led="switch.rogue_led"))["led"],
            "different_or_disabled_device",
        )

    def test_other_platform_is_not_falsely_associated(self):
        self.entries.append(entity("switch.other_platform", platform="mqtt"))
        self.assertNotIn("switch.other_platform", self.plan()["roles"]["led"]["options"])
        self.assertEqual(
            self.validate(dict(self.selected, led="switch.other_platform"))["led"],
            "different_or_disabled_device",
        )

    def test_disabled_and_hidden_entities_do_not_appear(self):
        self.entries += [
            entity("select.disabled", disabled="user"),
            entity("switch.hidden", hidden="integration"),
        ]
        p = self.plan()
        self.assertNotIn("select.disabled", p["roles"]["fan"]["options"])
        self.assertNotIn("switch.hidden", p["roles"]["led"]["options"])
        self.assertEqual(
            self.validate(dict(self.selected, fan="select.disabled"))["fan"],
            "different_or_disabled_device",
        )
        self.assertEqual(
            self.validate(dict(self.selected, led="switch.hidden"))["led"],
            "different_or_disabled_device",
        )

    def test_unknown_entity_and_invalid_domain_cannot_be_bound(self):
        self.assertEqual(
            self.validate(dict(self.selected, led="switch.absent"))["led"],
            "entity_not_registered",
        )
        self.assertEqual(
            self.validate(dict(self.selected, fan="switch.venta_led"))["fan"],
            "incompatible_entity_domain_or_class",
        )

    def test_ambiguous_same_device_candidates_require_manual_choice(self):
        self.entries.append(entity("switch.venta_led_2"))
        p = self.plan()
        self.assertEqual(p["roles"]["led"]["status"], "manual_choice")
        self.assertIsNone(p["roles"]["led"]["suggested"])
        self.assertEqual(len(p["roles"]["led"]["options"]), 2)

    def test_missing_role_never_triggers_device_command_or_submit(self):
        self.entries = [
            entry for entry in self.entries
            if entry.entity_id != "switch.venta_led"
        ]
        p = self.plan()
        self.assertEqual(p["roles"]["led"]["status"], "missing")
        self.assertFalse(p["can_submit"])
        self.assertEqual(self.validate()["led"], "entity_not_registered")

    def test_sensor_class_excludes_pm25_and_wrong_sensor(self):
        self.entries.append(entity("sensor.venta_pm25", device_class="pm25"))
        p = self.plan()
        for role in ("temperature", "humidity"):
            self.assertNotIn("sensor.venta_pm25", p["roles"][role]["options"])
            self.assertEqual(
                self.validate(dict(self.selected, **{role: "sensor.venta_pm25"}))[role],
                "incompatible_entity_domain_or_class",
            )
        self.assertEqual(
            self.validate(dict(self.selected, temperature="sensor.venta_humidity"))["temperature"],
            "incompatible_entity_domain_or_class",
        )

    def test_original_sensor_class_is_supported(self):
        self.entries = [
            entity(e.entity_id, device_class=None, original_class=e.device_class)
            if e.entity_id == "sensor.venta_temperature" else e
            for e in self.entries
        ]
        self.assertEqual(self.validate(), {})
        self.assertEqual(self.plan()["roles"]["temperature"]["status"], "confirm")

    def test_unclassified_sensor_requires_separate_user_confirmation(self):
        self.entries = [
            entity(e.entity_id, device_class=None)
            if e.entity_id == "sensor.venta_temperature" else e
            for e in self.entries
        ]
        p = self.plan()
        self.assertEqual(p["roles"]["temperature"]["status"], "review_class")
        self.assertIsNone(p["roles"]["temperature"]["suggested"])
        self.assertEqual(self.validate()["temperature"], "sensor_class_confirmation_required")
        self.assertEqual(
            self.validate(confirmed_unclassified=frozenset({"temperature"})), {}
        )

    def test_sensor_override_cannot_bypass_explicit_wrong_class(self):
        self.entries.append(entity("sensor.venta_pm25", device_class="pm25"))
        errors = self.validate(
            dict(self.selected, temperature="sensor.venta_pm25"),
            confirmed_unclassified=frozenset({"temperature"}),
        )
        self.assertEqual(errors["temperature"], "incompatible_entity_domain_or_class")

    def test_duplicate_field_bindings_are_rejected(self):
        self.assertEqual(
            self.validate(dict(self.selected, brightness="select.venta_fan"))["brightness"],
            "duplicate_entity",
        )

    def test_humidifier_cannot_be_selected_as_linked_entity(self):
        self.assertEqual(
            self.validate(dict(self.selected, fan=self.humidifier.entity_id))["fan"],
            "duplicate_entity",
        )

    def test_missing_or_extra_fields_fail_closed(self):
        partial = dict(self.selected)
        partial.pop("led")
        errors = self.validate(partial)
        self.assertEqual(errors["_form"], "all_five_roles_required")
        self.assertEqual(errors["led"], "required")
        extra = dict(self.selected, extra="switch.venta_led")
        self.assertEqual(self.validate(extra)["_form"], "all_five_roles_required")

    def test_invalid_confirmation_role_is_refused(self):
        self.assertEqual(
            self.validate(confirmed_unclassified=frozenset({"fan"}))["_confirmation"],
            "invalid_sensor_confirmation",
        )

    def test_duplicate_registry_data_fails_closed(self):
        self.entries.append(entity("switch.venta_led"))
        with self.assertRaises(discovery.DiscoveryError) as caught:
            self.plan()
        self.assertEqual(caught.exception.code, "duplicate_registry_entry")
        self.assertEqual(self.validate()["led"], "duplicate_registry_entry")

    def test_unregistered_humidifier_is_refused(self):
        with self.assertRaises(discovery.DiscoveryError) as caught:
            discovery.plan_from_entries(None, self.entries)
        self.assertEqual(caught.exception.code, "humidifier_not_registered")

    def test_other_platform_source_is_refused(self):
        self.humidifier.platform = "mqtt"
        with self.assertRaises(discovery.DiscoveryError) as caught:
            self.plan()
        self.assertEqual(caught.exception.code, "not_localtuya")

    def test_disabled_source_and_missing_device_and_config_refused(self):
        for attr, val, code in (
            ("disabled_by", "user", "humidifier_disabled"),
            ("device_id", None, "device_id_missing"),
            ("config_entry_id", None, "config_entry_missing"),
        ):
            original = getattr(self.humidifier, attr)
            setattr(self.humidifier, attr, val)
            with self.subTest(attr=attr), self.assertRaises(discovery.DiscoveryError) as error:
                self.plan()
            self.assertEqual(error.exception.code, code)
            setattr(self.humidifier, attr, original)

    def test_never_uses_entity_name_to_guess_a_different_device(self):
        self.entries.append(entity("switch.venta_led_like", device="fake-device-b"))
        p = self.plan()
        self.assertEqual(p["roles"]["led"]["options"], ["switch.venta_led"])

    def test_ha_adapter_reads_registry_and_revalidates_at_submission(self):
        registry = SimpleNamespace(async_get=lambda name: (
            self.humidifier if name == self.humidifier.entity_id else None
        ))
        holder = SimpleNamespace(entries=self.entries)
        ha_registry = types.ModuleType("homeassistant.helpers.entity_registry")
        ha_registry.async_get = lambda hass: registry
        ha_registry.async_entries_for_device = lambda _registry, device: list(holder.entries)
        ha = types.ModuleType("homeassistant")
        ha.__path__ = []
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.__path__ = []
        helpers.entity_registry = ha_registry
        with patch.dict(sys.modules, {
            "homeassistant": ha,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity_registry": ha_registry,
        }):
            plan = discovery.discover_from_hass(object(), self.humidifier.entity_id)
            self.assertEqual(plan["roles"]["led"]["options"], ["switch.venta_led"])
            self.assertEqual(
                discovery.validate_from_hass(object(), self.humidifier.entity_id, self.selected),
                {},
            )
            # Between loading the form and submission the entity is reassigned.
            holder.entries = [
                entity(e.entity_id, device="fake-device-b")
                if e.entity_id == self.selected["led"] else e
                for e in holder.entries
            ]
            errors = discovery.validate_from_hass(
                object(), self.humidifier.entity_id, self.selected
            )
            self.assertEqual(errors["led"], "different_or_disabled_device")


if __name__ == "__main__":
    unittest.main()
