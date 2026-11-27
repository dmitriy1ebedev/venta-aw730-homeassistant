"""Offline native control contract. Synthetic services, no HA or hardware."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/venta_homekit_native"
PACKAGE = "_venta_native_control_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(COMPONENT)]
with patch.dict(sys.modules, {PACKAGE: package}):
    spec = importlib.util.spec_from_file_location(PACKAGE + ".native_control", COMPONENT / "native_control.py")
    assert spec and spec.loader
    native = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = native
    spec.loader.exec_module(native)
    binding = sys.modules[PACKAGE + ".device_binding"]


class NativeControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.roles = {
            "humidifier": "humidifier.fixture", "fan": "select.fixture_fan",
            "led": "switch.fixture_led", "brightness": "select.fixture_brightness",
            "temperature": "sensor.fixture_temperature", "humidity": "sensor.fixture_humidity",
        }
        self.rows = {
            entity_id: NS(entity_id=entity_id, unique_id="fixture-" + role,
                          platform="localtuya", config_entry_id="source-config",
                          device_id="source-device", disabled_by=None, hidden_by=None)
            for role, entity_id in self.roles.items()
        }
        self.source = self.rows[self.roles["humidifier"]]
        self.device = NS(id="source-device", config_entry_id="source-config", disabled_by=None)
        self.entry = NS(entry_id="source-config", domain="localtuya", disabled_by=None)
        self.identity = binding.source_identity(self.source, self.device, self.entry)
        self.states = {
            self.roles["humidifier"]: NS(state="off", attributes={
                "humidity": 45, "mode": "Auto", "available_modes": list(native.MODES)}),
            self.roles["fan"]: NS(state="1", attributes={"options": list(native.FAN_OPTIONS)}),
            self.roles["led"]: NS(state="off", attributes={}),
            self.roles["brightness"]: NS(state="1", attributes={"options": list(native.LED_OPTIONS)}),
            self.roles["temperature"]: NS(state="23", attributes={}),
            self.roles["humidity"]: NS(state="48", attributes={}),
        }
        self.calls = []
        self.watchers = {}
        self.blocked_services = set()
        self.no_readback = set()
        self.after_call = None
        self.hass = NS(
            config_entries=NS(async_get_entry=lambda key: self.entry if key == self.entry.entry_id else None),
            states=self.states, services=NS(has_service=lambda d, s: (d, s) not in self.blocked_services,
                                            async_call=self.call),
        )
        homeassistant = types.ModuleType("homeassistant")
        helpers = types.ModuleType("homeassistant.helpers")
        core = types.ModuleType("homeassistant.core")
        core.callback = lambda fn: fn
        er = types.ModuleType("homeassistant.helpers.entity_registry")
        er.async_get = lambda _hass: NS(async_get=self.rows.get)
        dr = types.ModuleType("homeassistant.helpers.device_registry")
        dr.async_get = lambda _hass: NS(async_get=lambda key: self.device if key == self.device.id else None)
        ev = types.ModuleType("homeassistant.helpers.event")
        ev.async_track_state_change_event = self.subscribe
        homeassistant.helpers = helpers
        helpers.entity_registry, helpers.device_registry, helpers.event = er, dr, ev
        self.modules = patch.dict(sys.modules, {
            "homeassistant": homeassistant, "homeassistant.helpers": helpers,
            "homeassistant.core": core, "homeassistant.helpers.entity_registry": er,
            "homeassistant.helpers.device_registry": dr, "homeassistant.helpers.event": ev,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.controller = native.NativeControl(self.hass, self.identity, self.roles, readback_timeout=0.03)

    def subscribe(self, hass, entity_ids, callback):
        key = entity_ids[0]
        self.watchers.setdefault(key, []).append(callback)
        return lambda: self.watchers[key].remove(callback)

    async def call(self, domain, service, data, *, blocking, context):
        self.assertTrue(blocking)
        self.calls.append((domain, service, dict(data), context))
        state = self.states[data["entity_id"]]
        if (domain, service) not in self.no_readback:
            if service in ("turn_on", "turn_off"):
                state.state = "on" if service == "turn_on" else "off"
            elif service == "set_humidity":
                state.attributes["humidity"] = data["humidity"]
            elif service == "set_mode":
                state.attributes["mode"] = data["mode"]
            elif service == "select_option":
                state.state = data["option"]
            else:
                raise AssertionError("Unexpected service")
            for callback in list(self.watchers.get(data["entity_id"], [])):
                callback(None)
        if self.after_call:
            self.after_call(domain, service)

    def names(self):
        return [(d, s) for d, s, _, _ in self.calls]

    async def test_power_and_target_humidity_use_original_entity_and_context(self):
        context = object()
        await self.controller.power(True, context=context)
        await self.controller.target_humidity(60, context=context)
        self.assertEqual(self.names(), [("humidifier", "turn_on"), ("humidifier", "set_humidity")])
        self.assertEqual(self.calls[1][2], {"entity_id": self.roles["humidifier"], "humidity": 60})
        self.assertTrue(all(call[3] is context for call in self.calls))
        self.assertEqual(self.controller.state("humidifier").attributes["humidity"], 60)
        await self.controller.power(True)
        self.assertEqual(len(self.calls), 2)

    async def test_positive_fan_power_manual_and_speed_sequence(self):
        await self.controller.fan_percentage(80)
        self.assertEqual(self.names(), [("humidifier", "turn_on"),
            ("humidifier", "set_mode"), ("select", "select_option")])
        self.assertEqual(self.calls[1][2]["mode"], "Manual")
        self.assertEqual(self.calls[2][2], {"entity_id": self.roles["fan"], "option": "4"})
        await self.controller.fan_percentage(0)
        self.assertEqual(self.names()[-1], ("humidifier", "turn_off"))

    async def test_mode_never_implicitly_turns_on(self):
        with self.assertRaisesRegex(native.ControlError, "power_on_required"):
            await self.controller.mode("Sleep")
        self.assertFalse(self.calls)
        await self.controller.power(True)
        await self.controller.mode("Sleep")
        self.assertEqual(self.controller.state("humidifier").attributes["mode"], "Sleep")

    async def test_led_uses_confirmed_switch_and_eight_brightness_levels(self):
        await self.controller.led(True, 255)
        self.assertEqual(self.names(), [("switch", "turn_on"), ("select", "select_option")])
        self.assertEqual(self.calls[1][2], {"entity_id": self.roles["brightness"], "option": "8"})
        await self.controller.led(True, 0)
        self.assertEqual(self.names()[-1], ("switch", "turn_off"))
        self.assertEqual(self.controller.state("humidifier").state, "off")

    async def test_invalid_values_do_not_dispatch(self):
        cases = [
            (self.controller.power, (1,)), (self.controller.mode, ("Dry",)),
            (self.controller.target_humidity, (29,)), (self.controller.target_humidity, (71,)),
            (self.controller.target_humidity, (45.5,)),
            (self.controller.target_humidity, (float("nan"),)),
            (self.controller.target_humidity, (10**1000,)),
            (self.controller.fan_percentage, (True,)), (self.controller.fan_percentage, (101,)),
            (self.controller.led, (False, 50)), (self.controller.led, (True, 256)),
        ]
        for method, args in cases:
            with self.subTest(method=method.__name__), self.assertRaises(native.ControlError):
                await method(*args)
        self.assertEqual(self.calls, [])

    async def test_unavailable_and_wrong_role_prevent_any_write(self):
        self.states[self.roles["fan"]].state = "unavailable"
        with self.assertRaisesRegex(native.ControlError, "source_unavailable"):
            await self.controller.fan_percentage(80)
        self.states[self.roles["fan"]].state = "1"
        self.rows[self.roles["fan"]].device_id = "foreign-device"
        with self.assertRaisesRegex(native.ControlError, "role_binding_invalid"):
            await self.controller.fan_percentage(80)
        self.assertFalse(self.calls)

    async def test_same_device_replacement_is_rejected(self):
        self.rows[self.roles["led"]].unique_id = "another-switch"
        with self.assertRaisesRegex(native.ControlError, "role_identity_changed"):
            await self.controller.led(True)
        self.source.unique_id = "new-humidifier"
        with self.assertRaisesRegex(native.ControlError, "source_identity_changed"):
            await self.controller.power(True)
        self.assertFalse(self.calls)

    async def test_missing_service_or_changed_options_preflight(self):
        self.blocked_services.add(("select", "select_option"))
        with self.assertRaisesRegex(native.ControlError, "service_unavailable"):
            await self.controller.fan_percentage(80)
        self.blocked_services.clear()
        self.states[self.roles["fan"]].attributes["options"] = ["1", "2"]
        with self.assertRaisesRegex(native.ControlError, "source_options_changed"):
            await self.controller.fan_percentage(80)
        self.assertFalse(self.calls)

    async def test_readback_timeout_stops_followup_and_no_optimistic_state(self):
        self.no_readback.add(("humidifier", "turn_on"))
        with self.assertRaisesRegex(native.ControlError, "readback_timeout"):
            await self.controller.fan_percentage(80)
        self.assertEqual(self.names(), [("humidifier", "turn_on")])
        self.assertEqual(self.controller.state("humidifier").state, "off")
        self.assertTrue(all(not callbacks for callbacks in self.watchers.values()))

    async def test_rebinding_mid_command_stops_later_write(self):
        def replace(domain, service):
            if service == "turn_on":
                self.rows[self.roles["fan"]].unique_id = "rebound"
        self.after_call = replace
        with self.assertRaisesRegex(native.ControlError, "role_identity_changed"):
            await self.controller.fan_percentage(80)
        self.assertEqual(self.names(), [("humidifier", "turn_on")])

    async def test_persisted_role_pin_survives_constructor_and_rejects_replacement(self):
        pinned = self.controller.role_identities.copy()
        native.NativeControl(self.hass, self.identity, self.roles, expected_roles=pinned)
        self.rows[self.roles["brightness"]].unique_id = "new-brightness"
        with self.assertRaisesRegex(native.ControlError, "role_identity_changed"):
            native.NativeControl(self.hass, self.identity, self.roles, expected_roles=pinned)


if __name__ == "__main__":
    unittest.main()
