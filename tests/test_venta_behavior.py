"""Call-level regression tests for Venta HomeKit commands without a real device.

Import the actual integration with bounded Home Assistant/PyHAP stubs; no
hardware access, pairing state, LAN socket or HA runtime is involved.
A later test suite must exercise these behaviors against real HA/PyHAP APIs.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "venta_homekit_native"


class FakeState:
    def __init__(self, state: str, **attributes):
        self.state = state
        self.attributes = attributes


class FakeStates(dict):
    pass


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, dict(data), blocking))


class FakeCharacteristic:
    def __init__(self, value=None):
        self.value = value

    def set_value(self, value):
        self.value = value


class FakeHass:
    def __init__(self, entity, state):
        self.states = FakeStates({entity: state})
        self.services = FakeServices()
        self.tasks = []

    def async_create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    async def complete(self):
        if self.tasks:
            tasks = self.tasks[:]
            self.tasks.clear()
            await asyncio.gather(*tasks)


class FakeNativeHumidifier:
    def _set_chars(self, values):
        self.parent_chars = dict(values)


def _load_venta_with_stubs():
    fake = {}

    def package(name):
        m = types.ModuleType(name)
        m.__path__ = []
        fake[name] = m
        return m

    def module(name, **members):
        m = types.ModuleType(name)
        m.__dict__.update(members)
        fake[name] = m
        return m

    package("homeassistant")
    package("homeassistant.components")
    package("homeassistant.components.homekit")
    package("homeassistant.helpers")
    package("pyhap")
    vol = module(
        "voluptuous",
        Schema=lambda *a, **k: object(),
        Required=lambda key: key,
        Optional=lambda key: key,
        ALLOW_EXTRA=object(),
    )
    module("homeassistant.helpers.config_validation", entity_id=str, string=str)
    module("pyhap.util", callback=lambda fn: fn)
    module(
        "homeassistant.const",
        ATTR_ENTITY_ID="entity_id",
        EVENT_HOMEASSISTANT_STARTED="started",
        STATE_OFF="off",
        STATE_ON="on",
    )
    module(
        "homeassistant.core",
        Event=object,
        HassJobType=types.SimpleNamespace(Callback="callback"),
        HomeAssistant=object,
        State=FakeState,
        callback=lambda fn: fn,
    )
    module("homeassistant.helpers.dispatcher", async_dispatcher_send=lambda *a: None)
    module("homeassistant.helpers.event", async_track_state_change_event=lambda *a, **k: None)
    module("homeassistant.components.homekit.accessories", TYPES={"HumidifierDehumidifier": FakeNativeHumidifier})
    module("homeassistant.components.homekit.const", SIGNAL_RELOAD_ENTITIES="reload_{}", STATUS_RUNNING="running")
    module("homeassistant.components.homekit.type_humidifiers", HumidifierDehumidifier=FakeNativeHumidifier)
    # Load a unique package name so no test substitutes anything in live HA.
    name = "_venta_behavior_test_package"
    spec = importlib.util.spec_from_file_location(
        name, INTEGRATION / "__init__.py",
        submodule_search_locations=[str(INTEGRATION)],
    )
    assert spec is not None and spec.loader is not None
    entry = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake):
        sys.modules[name] = entry
        spec.loader.exec_module(entry)
    return entry


class VentaCommandBehaviorTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.integration = _load_venta_with_stubs()

    def setUp(self):
        self.entity = "humidifier.venta_ci_fake"
        self.fan = "select.venta_ci_fan"
        self.led = "switch.venta_ci_led"
        self.brightness = "select.venta_ci_brightness"
        self.temp = "sensor.venta_ci_temperature"
        self.integration.ENTITY = self.entity
        self.integration.FAN = self.fan
        self.integration.LED = self.led
        self.integration.BRIGHTNESS = self.brightness
        self.integration.TEMPERATURE = self.temp
        self.hass = FakeHass(self.entity, FakeState("on", mode="Manual"))
        self.accessory = self.integration.VentaEnhancedHumidifier.__new__(
            self.integration.VentaEnhancedHumidifier
        )
        self.accessory.hass = self.hass
        self.accessory.entity_id = self.entity
        self.accessory.calls = []
        self.accessory.async_call_service = lambda domain, action, data, reason: self.accessory.calls.append(
            (domain, action, dict(data), reason)
        )

    def assert_services(self, *expected):
        self.assertEqual(
            [(domain, name) for domain, name, _data, _blocking in self.hass.services.calls],
            list(expected),
        )
        self.assertTrue(all(blocking for *_, blocking in self.hass.services.calls))

    async def test_power_on_before_target_and_auto_manual_modes(self):
        self.hass.states[self.entity] = FakeState("off", mode="Manual")
        await self.accessory._venta_apply_target(0)
        self.assert_services(("humidifier", "turn_on"), ("humidifier", "set_mode"))
        self.assertEqual(self.hass.services.calls[-1][2]["mode"], "Auto")
        self.hass.services.calls.clear()
        self.hass.states[self.entity] = FakeState("on", mode="Auto")
        await self.accessory._venta_apply_target(1)
        self.assert_services(("humidifier", "set_mode"))
        self.assertEqual(self.hass.services.calls[-1][2]["mode"], "Manual")

    async def test_unavailable_skips_control_commands(self):
        for state in ("unknown", "unavailable"):
            self.hass.states[self.entity] = FakeState(state, mode="Manual")
            await self.accessory._venta_apply_target(0)
            await self.accessory._venta_apply_fan({"RotationSpeed": 60})
            self.assertEqual(self.hass.services.calls, [])

    async def test_auto_off_returns_to_manual_only_when_running(self):
        self.hass.states[self.entity] = FakeState("on", mode="Auto")
        await self.accessory._venta_apply_auto_toggle(False)
        self.assert_services(("humidifier", "set_mode"))
        self.assertEqual(self.hass.services.calls[-1][2]["mode"], "Manual")
        self.hass.services.calls.clear()
        for state, mode in (("off", "Auto"), ("on", "Manual")):
            self.hass.states[self.entity] = FakeState(state, mode=mode)
            await self.accessory._venta_apply_auto_toggle(False)
            self.assertEqual(self.hass.services.calls, [])
        self.hass.states[self.entity] = FakeState("off", mode="Manual")
        await self.accessory._venta_apply_auto_toggle(True)
        self.assert_services(("humidifier", "turn_on"), ("humidifier", "set_mode"))

    async def test_all_five_manual_fan_speeds_and_power_off(self):
        for index in range(1, 6):
            self.hass.services.calls.clear()
            self.hass.states[self.entity] = FakeState("on", mode="Manual")
            await self.accessory._venta_apply_fan({"RotationSpeed": index * 20})
            self.assert_services(("humidifier", "set_mode"), ("select", "select_option"))
            self.assertEqual(self.hass.services.calls[-1][2], {"entity_id": self.fan, "option": str(index)})
            self.assertEqual(self.hass.services.calls[0][2]["mode"], "Manual")
        self.hass.services.calls.clear()
        self.hass.states[self.entity] = FakeState("off", mode="Manual")
        await self.accessory._venta_apply_fan({"RotationSpeed": 80})
        self.assert_services(("humidifier", "turn_on"), ("humidifier", "set_mode"), ("select", "select_option"))
        self.hass.services.calls.clear()
        await self.accessory._venta_apply_fan({"Active": 0})
        self.assert_services(("humidifier", "turn_off"))
        self.hass.services.calls.clear()
        await self.accessory._venta_apply_fan({"RotationSpeed": 0})
        self.assert_services(("humidifier", "turn_off"))

    async def test_auto_fan_target_and_target_scheduled_from_homekit(self):
        await self.accessory._venta_apply_fan({"TargetFanState": 1})
        self.assert_services(("humidifier", "set_mode"))
        self.assertEqual(self.hass.services.calls[0][2]["mode"], "Auto")
        self.hass.services.calls.clear()
        self.accessory.char_target_humidifier_dehumidifier = FakeCharacteristic()
        self.accessory._set_chars({"TargetHumidifierDehumidifierState": 0, "CurrentRelativeHumidity": 52})
        await self.hass.complete()
        self.assertEqual(self.accessory.char_target_humidifier_dehumidifier.value, 0)
        self.assertEqual(self.accessory.parent_chars, {"CurrentRelativeHumidity": 52})
        self.assert_services(("humidifier", "set_mode"))

    async def test_sleep_state_readback_and_sensor_mapping(self):
        self.hass.states[self.entity] = FakeState("on", mode="Sleep")
        self.hass.states[self.fan] = FakeState("4")
        self.hass.states[self.led] = FakeState("on")
        self.hass.states[self.brightness] = FakeState("6")
        self.hass.states[self.temp] = FakeState("23.5")
        a = self.accessory
        a._venta_fan_active = FakeCharacteristic()
        a._venta_auto_on = FakeCharacteristic()
        a._venta_fan_current = FakeCharacteristic()
        a._venta_fan_target = FakeCharacteristic()
        a._venta_fan_speed = FakeCharacteristic()
        a._venta_led_on = FakeCharacteristic()
        a._venta_led_brightness = FakeCharacteristic()
        a._venta_temperature = FakeCharacteristic()
        a._venta_update_extras()
        self.assertEqual(a._venta_fan_active.value, 1)
        self.assertEqual(a._venta_auto_on.value, False)
        self.assertEqual(a._venta_fan_target.value, 0)
        self.assertEqual(a._venta_fan_speed.value, 80)
        self.assertEqual(a._venta_led_on.value, True)
        self.assertEqual(a._venta_led_brightness.value, 75)
        self.assertEqual(a._venta_temperature.value, 23.5)
        self.assertEqual(self.hass.services.calls, [])

    async def test_led_power_and_brightness_map_to_existing_entities(self):
        self.accessory._venta_set_led({"On": True, "Brightness": 100})
        self.assertEqual(self.accessory.calls[0][:3], ("switch", "turn_on", {"entity_id": self.led}))
        self.assertEqual(self.accessory.calls[1][:3], ("select", "select_option", {"entity_id": self.brightness, "option": "8"}))
        self.accessory.calls.clear()
        self.accessory._venta_set_led({"On": False, "Brightness": 1})
        self.assertEqual(self.accessory.calls[0][1], "turn_off")
        self.assertEqual(self.accessory.calls[1][2]["option"], "1")


if __name__ == "__main__":
    unittest.main()
