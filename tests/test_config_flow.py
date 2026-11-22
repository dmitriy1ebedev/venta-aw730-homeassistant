"""Offline tests for the Venta UI wizard with synthetic HA registries only."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "venta_homekit_native"
DOMAIN = "venta_homekit_native"


def entity(name, *, device="venta-device", config="localtuya-config",
           device_class=None, disabled=None):
    return SimpleNamespace(
        entity_id=name, device_id=device, config_entry_id=config,
        platform="localtuya", device_class=device_class,
        original_device_class=None, disabled_by=disabled, hidden_by=None,
    )


class FakeConfigFlow:
    """Enough of HA's flow contract for deterministic offline testing."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        self.existing_entries = []
        self.unique_id = None

    def _async_current_entries(self):
        return self.existing_entries

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        if self.existing_entries:
            raise AssertionError("duplicate entry must be rejected sooner")

    def async_show_form(self, *, step_id, data_schema, errors):
        return {
            "type": "form", "step_id": step_id,
            "schema": data_schema, "errors": errors,
        }

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}


class VentaFlowTests(unittest.TestCase):
    def setUp(self):
        pkg = types.ModuleType("venta_flow_test_package")
        pkg.__path__ = [str(INTEGRATION)]
        pkg.DOMAIN = DOMAIN

        ha = types.ModuleType("homeassistant")
        ha.__path__ = []
        ha_config = types.ModuleType("homeassistant.config_entries")
        ha_config.ConfigFlow = FakeConfigFlow
        ha.config_entries = ha_config
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.__path__ = []
        registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
        registry_module.async_get = lambda hass: hass.registry
        registry_module.async_entries_for_device = (
            lambda registry, device: [
                e for e in registry.entities.values()
                if e.device_id == device
            ]
        )
        helpers.entity_registry = registry_module
        ha.helpers = helpers

        vol = types.ModuleType("voluptuous")
        vol.Schema = lambda schema: schema
        vol.Required = lambda key, default=None: key
        vol.Optional = lambda key, default=None: key
        vol.In = lambda values: values

        modules = {
            pkg.__name__: pkg,
            "homeassistant": ha,
            "homeassistant.config_entries": ha_config,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity_registry": registry_module,
            "voluptuous": vol,
        }
        mocked = patch.dict(sys.modules, modules)
        mocked.start()
        self.addCleanup(mocked.stop)
        spec = importlib.util.spec_from_file_location(
            pkg.__name__ + ".config_flow", INTEGRATION / "config_flow.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

        self.entities = {
            item.entity_id: item for item in [
                entity("humidifier.venta_fixture"),
                entity("select.fan_speed"),
                entity("select.led_brightness"),
                entity("switch.led_power"),
                entity("sensor.temp", device_class="temperature"),
                entity("sensor.humidity", device_class="humidity"),
            ]
        }
        self.bridges = [
            SimpleNamespace(
                entry_id="existing-bridge",
                title="Existing HomeKit Bridge",
                options={
                    "mode": "bridge",
                    "filter": {"include_entities": ["humidifier.venta_fixture"]},
                },
            )
        ]
        self.hass = SimpleNamespace(
            data={},
            registry=SimpleNamespace(
                entities=self.entities,
                async_get=lambda key: self.entities.get(key),
            ),
            config_entries=SimpleNamespace(
                async_entries=lambda domain: (
                    self.bridges if domain == "homekit" else []
                ),
            ),
        )
        self.flow = self.module.VentaConfigFlow()
        self.flow.hass = self.hass
        self.mapping = {
            "fan_entity": "select.fan_speed",
            "led_entity": "switch.led_power",
            "brightness_entity": "select.led_brightness",
            "temperature_entity": "sensor.temp",
            "humidity_entity": "sensor.humidity",
        }

    def run_flow(self, coro):
        return asyncio.run(coro)

    def choose_device(self):
        return self.run_flow(self.flow.async_step_user({
            "humidifier_entity": "humidifier.venta_fixture",
            "bridge_entry_id": "existing-bridge",
        }))

    def test_start_offers_existing_device_and_bridge(self):
        r = self.run_flow(self.flow.async_step_user())
        self.assertEqual((r["type"], r["step_id"]), ("form", "user"))
        self.assertEqual(
            list(r["schema"]["humidifier_entity"]), ["humidifier.venta_fixture"]
        )
        self.assertEqual(
            r["schema"]["bridge_entry_id"]["existing-bridge"],
            "Existing HomeKit Bridge",
        )

    def test_explicit_selection_creates_one_entry_without_device_commands(self):
        self.assertEqual(self.choose_device()["step_id"], "entities")
        result = self.run_flow(self.flow.async_step_entities(self.mapping))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["bridge_entry_id"], "existing-bridge")
        self.assertEqual(result["data"]["fan_entity"], "select.fan_speed")
        self.assertEqual(self.flow.unique_id, "humidifier.venta_fixture")

    def test_no_localtuya_humidifier_aborts(self):
        self.entities.pop("humidifier.venta_fixture")
        self.assertEqual(
            self.run_flow(self.flow.async_step_user())["reason"],
            "localtuya_humidifier_missing",
        )

    def test_no_existing_homekit_bridge_aborts(self):
        self.bridges.clear()
        self.assertEqual(
            self.run_flow(self.flow.async_step_user())["reason"],
            "homekit_bridge_missing",
        )

    def test_bridge_in_accessory_mode_not_offered(self):
        self.bridges[0].options["mode"] = "accessory"
        self.assertEqual(
            self.run_flow(self.flow.async_step_user())["reason"],
            "homekit_bridge_missing",
        )

    def test_bridge_excluding_humidifier_refused(self):
        self.bridges[0].options["filter"]["include_entities"] = ["light.other"]
        r = self.choose_device()
        self.assertEqual(r["errors"]["bridge_entry_id"],
                         "bridge_excludes_humidifier")

    def test_disappearing_bridge_aborts_before_save(self):
        self.choose_device()
        self.bridges.clear()
        r = self.run_flow(self.flow.async_step_entities(self.mapping))
        self.assertEqual(r["reason"], "bridge_unavailable")

    def test_invalid_user_step_does_not_store_selection(self):
        r = self.run_flow(self.flow.async_step_user({
            "humidifier_entity": "humidifier.different",
            "bridge_entry_id": "missing",
        }))
        self.assertEqual(r["type"], "form")
        self.assertEqual(len(r["errors"]), 2)
        self.assertIsNone(self.flow._humidifier)

    def test_other_device_cannot_be_selected(self):
        self.choose_device()
        self.entities["switch.other_led"] = entity(
            "switch.other_led", device="another-device"
        )
        r = self.run_flow(self.flow.async_step_entities({
            **self.mapping, "led_entity": "switch.other_led",
        }))
        self.assertEqual(r["errors"]["led_entity"], "invalid_entity")

    def test_stale_registry_device_move_is_rechecked(self):
        self.choose_device()
        self.entities["switch.led_power"].device_id = "another-device"
        r = self.run_flow(self.flow.async_step_entities(self.mapping))
        # Role is no longer available at all: fail closed before submission.
        self.assertEqual(r["reason"], "required_entities_missing")

    def test_stale_registry_disappearance_is_rechecked(self):
        self.choose_device()
        self.entities.pop("switch.led_power")
        r = self.run_flow(self.flow.async_step_entities(self.mapping))
        self.assertEqual(r["reason"], "required_entities_missing")

    def test_duplicate_entity_role_rejected(self):
        self.choose_device()
        r = self.run_flow(self.flow.async_step_entities({
            **self.mapping, "brightness_entity": "select.fan_speed"
        }))
        self.assertEqual(r["errors"]["brightness_entity"], "invalid_entity")

    def test_unclassified_sensor_requires_confirmed_review(self):
        self.entities["sensor.temp"].device_class = None
        self.choose_device()
        missing = self.run_flow(self.flow.async_step_entities(self.mapping))
        self.assertEqual(missing["errors"]["temperature_entity"], "invalid_entity")
        confirmed = self.run_flow(self.flow.async_step_entities({
            **self.mapping, "confirm_temperature": True
        }))
        self.assertEqual(confirmed["type"], "create_entry")
        self.assertEqual(confirmed["data"]["confirmed_unclassified"], ["temperature"])

    def test_yaml_existing_patch_prevents_new_config(self):
        self.hass.data[DOMAIN] = {"patched": True}
        self.assertEqual(
            self.run_flow(self.flow.async_step_user())["reason"],
            "single_instance_allowed",
        )

    def test_existing_entry_prevents_duplicate(self):
        self.flow.existing_entries = [object()]
        self.assertEqual(
            self.run_flow(self.flow.async_step_user())["reason"],
            "single_instance_allowed",
        )

    def test_retry_after_bad_selection_is_allowed(self):
        self.choose_device()
        bad = self.run_flow(self.flow.async_step_entities({
            **self.mapping, "led_entity": "switch.missing",
        }))
        self.assertEqual(bad["type"], "form")
        good = self.run_flow(self.flow.async_step_entities(self.mapping))
        self.assertEqual(good["type"], "create_entry")


    def legacy_yaml_fixture(self):
        values = {
            "humidifier_entity": "humidifier.venta_fixture",
            "bridge_title": "Existing HomeKit Bridge",
            "bridge_entry_id": "existing-bridge",
            **self.mapping,
        }
        self.hass.data[DOMAIN] = {
            "patched": True,
            "legacy_yaml": values,
        }
        return values

    def migrate(self, **changes):
        return self.run_flow(self.flow.async_step_migrate_yaml({
            "confirm_backup": True,
            "confirm_remove_yaml_and_restart": True,
            **changes,
        }))

    def test_active_yaml_offers_migration_instead_of_duplicate_wizard(self):
        self.legacy_yaml_fixture()
        r = self.run_flow(self.flow.async_step_user())
        self.assertEqual((r["type"], r["step_id"]), ("form", "migrate_yaml"))
        self.assertNotIn("humidifier_entity", r["schema"])

    def test_automatic_yaml_import_aborts_without_writing(self):
        self.legacy_yaml_fixture()
        r = self.run_flow(self.flow.async_step_import({}))
        self.assertEqual(r["reason"], "interactive_yaml_migration_required")

    def test_migration_requires_both_explicit_confirmations(self):
        self.legacy_yaml_fixture()
        bad = self.run_flow(self.flow.async_step_migrate_yaml({
            "confirm_backup": True,
            "confirm_remove_yaml_and_restart": False,
        }))
        self.assertEqual(bad["type"], "form")
        self.assertEqual(bad["errors"]["base"], "yaml_migration_confirmation_required")
        self.assertIsNone(self.flow.unique_id)

    def test_migration_preserves_seven_yaml_values_and_exact_bridge_id(self):
        old = self.legacy_yaml_fixture()
        result = self.migrate()
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["migration_from_yaml"], True)
        self.assertEqual(result["data"]["bridge_entry_id"], "existing-bridge")
        self.assertEqual(result["data"]["confirmed_unclassified"], [])
        for key, value in old.items():
            self.assertEqual(result["data"][key], value)
        self.assertEqual(self.hass.data[DOMAIN]["legacy_yaml"], old)
        self.assertEqual(self.flow.unique_id, old["humidifier_entity"])

    def test_existing_config_entry_blocks_repeated_migration(self):
        self.legacy_yaml_fixture()
        self.flow.existing_entries.append(object())
        self.assertEqual(self.migrate()["reason"], "single_instance_allowed")

    def test_yaml_device_ownership_change_blocks_migration(self):
        self.legacy_yaml_fixture()
        self.run_flow(self.flow.async_step_user())
        self.entities["switch.led_power"].device_id = "other-device"
        r = self.migrate()
        self.assertEqual(r["reason"], "required_entities_missing")
        self.assertIsNone(self.flow.unique_id)

    def test_yaml_migration_rejects_changed_bridge_id(self):
        values = self.legacy_yaml_fixture()
        self.run_flow(self.flow.async_step_user())
        values["bridge_entry_id"] = "different-bridge"
        r = self.migrate()
        self.assertEqual(r["reason"], "yaml_migration_unavailable")

    def test_yaml_migration_rejects_missing_bridge(self):
        self.legacy_yaml_fixture()
        self.bridges.clear()
        self.assertEqual(self.migrate()["reason"], "bridge_unavailable")

    def test_yaml_migration_unclassified_sensor_needs_explicit_review(self):
        self.legacy_yaml_fixture()
        self.entities["sensor.temp"].device_class = None
        first = self.run_flow(self.flow.async_step_migrate_yaml())
        self.assertIn("confirm_temperature", first["schema"])
        bad = self.migrate()
        self.assertEqual(bad["errors"]["base"], "yaml_migration_entities_changed")
        good = self.migrate(confirm_temperature=True)
        self.assertEqual(good["type"], "create_entry")
        self.assertEqual(good["data"]["confirmed_unclassified"], ["temperature"])

    def test_yaml_flow_rejects_missing_active_patch(self):
        self.hass.data[DOMAIN] = {"legacy_yaml": {"humidifier_entity": "x"}}
        self.assertEqual(
            self.migrate()["reason"], "yaml_migration_unavailable"
        )


if __name__ == "__main__":
    unittest.main()
