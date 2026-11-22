"""Config entry lifecycle regression without LocalTuya, HomeKit network or pairing.

Tests the real integration entrypoints with a synthetic HA instance and a
strict fake device registry. No physical device commands or service mutations.
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_venta_behavior import _load_venta_with_stubs, FakeNativeHumidifier

DOMAIN = "venta_homekit_native"


class _Services:
    def __init__(self):
        self.registered = []

    def async_register(self, domain, name, handler, **kwargs):
        self.registered.append((domain, name))

    async def async_call(self, *args, **kwargs):
        raise AssertionError("No device calls permitted in config entry setup")


class _Hass:
    def __init__(self, bridge, config_dir):
        self.data = {}
        self.services = _Services()
        self.config = SimpleNamespace(config_dir=config_dir)
        self.config_entries = SimpleNamespace(
            async_entries=lambda domain: [bridge] if domain == "homekit" else []
        )
        self.bus = SimpleNamespace(
            async_listen_once=lambda *args, **kwargs: None
        )
        self.is_running = False
        self.executor_calls = 0
        self.tasks = []

    async def async_add_executor_job(self, fn, *args):
        # Count calls but never write a real LocalTuya template in this fixture.
        self.executor_calls += 1
        return "fixture_skip_managed_template_write"

    def async_create_task(self, coro):
        raise AssertionError("No reload/pairing task may start in synthetic setup")


class VentaConfigEntryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.integration = _load_venta_with_stubs()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = {
            "humidifier_entity": "humidifier.fixture_venta",
            "bridge_title": "Synthetic HomeKit Bridge",
            "bridge_entry_id": "existing-bridge",
            "fan_entity": "select.fixture_fan",
            "led_entity": "switch.fixture_led",
            "brightness_entity": "select.fixture_brightness",
            "temperature_entity": "sensor.fixture_temperature",
            "humidity_entity": "sensor.fixture_humidity",
            "confirmed_unclassified": [],
        }
        self.bridge = SimpleNamespace(
            entry_id="existing-bridge",
            title="Synthetic HomeKit Bridge",
            options={
                "mode": "bridge",
                "filter": {
                    "include_entities": [self.data["humidifier_entity"]]
                },
            },
        )
        self.hass = _Hass(self.bridge, self.temp.name)
        self.entry = SimpleNamespace(entry_id="venta-ui-fixture-1", data=self.data)
        self.discovery_name = self.integration.__name__ + ".entity_discovery"
        discovery = types.ModuleType(self.discovery_name)
        discovery.DiscoveryError = type("DiscoveryError", (ValueError,), {})
        self.validated = []

        def validate(hass, source, selection, *, confirmed_unclassified=frozenset()):
            self.validated.append((source, dict(selection), confirmed_unclassified))
            if source != self.data["humidifier_entity"]:
                return {"humidifier": "wrong_humidifier"}
            return {}

        discovery.validate_from_hass = validate
        self.discovery_patch = patch.dict(sys.modules, {self.discovery_name: discovery})
        self.discovery_patch.start()
        self.addCleanup(self.discovery_patch.stop)

    async def test_no_yaml_start_is_inert(self):
        self.assertTrue(await self.integration.async_setup(self.hass, {}))
        self.assertEqual(self.hass.data, {})
        self.assertEqual(self.hass.services.registered, [])
        self.assertIs(self.integration.TYPES["HumidifierDehumidifier"], FakeNativeHumidifier)

    async def test_first_ui_setup_reuses_native_bridge_without_new_entities(self):
        self.assertTrue(await self.integration.async_setup(self.hass, {}))
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.integration.ENTITY, self.data["humidifier_entity"])
        self.assertEqual(self.integration.BRIDGE_ENTRY, self.bridge.entry_id)
        self.assertEqual(self.integration.LED, self.data["led_entity"])
        self.assertIs(
            self.integration.TYPES["HumidifierDehumidifier"],
            self.integration._venta_accessory_factory,
        )
        self.assertEqual(self.hass.data[DOMAIN]["config_entry_id"], self.entry.entry_id)
        self.assertEqual(self.hass.data[DOMAIN]["config_entry_data"], self.data)
        self.assertEqual(self.hass.executor_calls, 1)
        self.assertEqual(len(self.hass.services.registered), 2)
        self.assertEqual(self.hass.tasks, [])
        self.assertEqual(len(self.validated), 1)

    async def test_repeated_entry_setup_is_idempotent(self):
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.hass.executor_calls, 1)
        self.assertEqual(len(self.hass.services.registered), 2)
        self.assertEqual(len(self.validated), 2)

    async def test_other_config_entry_cannot_take_over_same_bridge(self):
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        other = SimpleNamespace(entry_id="second-entry", data=dict(self.data))
        self.assertFalse(await self.integration.async_setup_entry(self.hass, other))
        self.assertEqual(self.hass.data[DOMAIN]["config_entry_id"], self.entry.entry_id)
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_reconfigured_entry_cannot_silently_switch_led_binding(self):
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        changed = dict(self.data, led_entity="switch.another_localtuya_led")
        edited = SimpleNamespace(entry_id=self.entry.entry_id, data=changed)
        self.assertFalse(await self.integration.async_setup_entry(self.hass, edited))
        self.assertEqual(self.integration.LED, self.data["led_entity"])
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_yaml_patch_blocks_parallel_ui_owner(self):
        legacy = {k: v for k, v in self.data.items() if k != "confirmed_unclassified"}
        self.assertTrue(await self.integration.async_setup(self.hass, {DOMAIN: legacy}))
        self.assertFalse(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertNotIn("config_entry_id", self.hass.data[DOMAIN])
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_yaml_repeated_setup_rejects_mutating_linked_roles(self):
        legacy = {k: v for k, v in self.data.items() if k != "confirmed_unclassified"}
        self.assertTrue(await self.integration.async_setup(self.hass, {DOMAIN: legacy}))
        changed = dict(legacy, fan_entity="select.different_fan")
        self.assertFalse(await self.integration.async_setup(self.hass, {DOMAIN: changed}))
        self.assertEqual(self.integration.FAN, legacy["fan_entity"])
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_missing_bridge_fails_before_global_patch(self):
        self.entry.data = dict(self.data, bridge_entry_id="missing-bridge")
        self.assertFalse(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.hass.data, {})
        self.assertIs(self.integration.TYPES["HumidifierDehumidifier"], FakeNativeHumidifier)

    async def test_excluded_humidifier_fails_before_global_patch(self):
        self.bridge.options["filter"]["exclude_entities"] = [
            self.data["humidifier_entity"]
        ]
        self.assertFalse(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertIs(self.integration.TYPES["HumidifierDehumidifier"], FakeNativeHumidifier)

    async def test_api_drift_rejects_setup_before_global_patch(self):
        with patch.object(self.integration, "_homekit_apis_compatible", return_value=False):
            self.assertFalse(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.hass.services.registered, [])
        self.assertEqual(self.hass.data, {})
        self.assertIs(self.integration.TYPES["HumidifierDehumidifier"], FakeNativeHumidifier)

    async def test_unload_fails_closed_when_bridge_still_active(self):
        self.assertTrue(await self.integration.async_unload_entry(self.hass, self.entry))
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertFalse(await self.integration.async_unload_entry(self.hass, self.entry))
        self.assertIs(
            self.integration.TYPES["HumidifierDehumidifier"],
            self.integration._venta_accessory_factory,
        )
        self.assertEqual(self.hass.tasks, [])


    async def test_yaml_snapshot_pins_existing_homekit_bridge_for_ui_migration(self):
        legacy = {
            key: value for key, value in self.data.items()
            if key not in ("bridge_entry_id", "confirmed_unclassified")
        }
        self.assertTrue(await self.integration.async_setup(self.hass, {DOMAIN: legacy}))
        snapshot = self.hass.data[DOMAIN]["legacy_yaml"]
        self.assertEqual(snapshot["bridge_entry_id"], self.bridge.entry_id)
        self.assertEqual(set(snapshot), set(legacy) | {"bridge_entry_id"})
        self.assertEqual(
            {k: snapshot[k] for k in legacy}, legacy
        )
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_ui_entry_created_from_yaml_does_not_preempt_running_yaml(self):
        legacy = {
            key: value for key, value in self.data.items()
            if key not in ("bridge_entry_id", "confirmed_unclassified")
        }
        self.assertTrue(await self.integration.async_setup(self.hass, {DOMAIN: legacy}))
        proposed = SimpleNamespace(
            entry_id="proposed-entry",
            data=dict(self.data, migration_from_yaml=True),
        )
        self.assertFalse(await self.integration.async_setup_entry(self.hass, proposed))
        self.assertNotIn("config_entry_id", self.hass.data[DOMAIN])
        self.assertEqual(self.integration.BRIDGE_ENTRY, self.bridge.entry_id)
        self.assertEqual(self.integration.LED, self.data["led_entity"])
        self.assertEqual(self.hass.executor_calls, 1)

    async def test_rollback_to_yaml_with_existing_ui_entry_keeps_identity(self):
        legacy = {
            key: value for key, value in self.data.items()
            if key not in ("bridge_entry_id", "confirmed_unclassified")
        }
        self.assertTrue(await self.integration.async_setup(self.hass, {DOMAIN: legacy}))
        proposed = SimpleNamespace(
            entry_id="proposed-entry",
            data=dict(self.data, migration_from_yaml=True),
        )
        self.assertFalse(await self.integration.async_setup_entry(self.hass, proposed))
        # A restart with the original YAML present must restore the YAML
        # controller rather than taking over the existing HAP accessory.
        restarted = _load_venta_with_stubs()
        another_hass = _Hass(self.bridge, self.temp.name)
        self.assertTrue(await restarted.async_setup(another_hass, {DOMAIN: legacy}))
        self.assertFalse(await restarted.async_setup_entry(another_hass, proposed))
        self.assertEqual(restarted.BRIDGE_ENTRY, self.bridge.entry_id)
        self.assertEqual(restarted.ENTITY, legacy["humidifier_entity"])
        self.assertNotIn("config_entry_id", another_hass.data[DOMAIN])
        self.assertEqual(len(another_hass.services.registered), 2)


if __name__ == "__main__":
    unittest.main()
