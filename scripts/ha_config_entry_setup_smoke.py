"""Real HA/PyHAP API smoke for Venta config-entry setup and replay.

Disposable HA 2026.11.x container, --network none, synthetic in-memory
registries. No HAP server, no pairing, no LocalTuya service, no HA storage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class FakeServices:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str]] = []

    def async_register(self, domain, action, handler, **kwargs) -> None:
        self.registered.append((domain, action))

    async def async_call(self, *args, **kwargs) -> None:
        raise AssertionError("No physical device command is permitted")


class FakeHass:
    def __init__(self, bridge) -> None:
        self.data = {}
        self.config = SimpleNamespace(config_dir="/config")
        self.config_entries = SimpleNamespace(
            async_entries=lambda domain, *args, **kwargs:
                [bridge] if domain == "homekit" else []
        )
        self.services = FakeServices()
        self.is_running = False
        self.bus = SimpleNamespace(
            async_listen_once=lambda *args, **kwargs: None
        )
        self.executor_calls = 0
        self.scheduled = []

    async def async_add_executor_job(self, fn, *args):
        # No filesystem writes or LocalTuya template installation in this smoke.
        self.executor_calls += 1
        return "read_only_fixture"

    def async_create_task(self, coroutine):
        raise AssertionError("Unexpected HomeKit reload or async task")


def validate(config: Path, expected_ha_version: str) -> dict:
    from homeassistant.const import __version__ as ha_version
    from homeassistant.helpers import entity_registry as er
    from homeassistant.components.homekit.accessories import TYPES
    from homeassistant.components.homekit.type_humidifiers import (
        HumidifierDehumidifier as NativeHumidifier,
    )

    assert ha_version == expected_ha_version
    sys.path.insert(0, str(config))
    import custom_components.venta_homekit_native as venta

    assert TYPES.get("HumidifierDehumidifier") is NativeHumidifier
    values = {
        "humidifier_entity": "humidifier.venta_ci_fixture",
        "bridge_title": "Existing CI HomeKit bridge",
        "bridge_entry_id": "ci-homekit-bridge",
        "fan_entity": "select.ci_fan",
        "led_entity": "switch.ci_led",
        "brightness_entity": "select.ci_brightness",
        "temperature_entity": "sensor.ci_temperature",
        "humidity_entity": "sensor.ci_humidity",
        "confirmed_unclassified": [],
    }
    bridge = SimpleNamespace(
        entry_id=values["bridge_entry_id"],
        title=values["bridge_title"],
        options={
            "mode": "bridge",
            "filter": {
                "include_entities": [values["humidifier_entity"]],
            },
        },
    )

    def entry(name, cls=None):
        return SimpleNamespace(
            entity_id=name, device_id="ci-venta-device",
            config_entry_id="ci-localtuya-entry",
            platform="localtuya", device_class=cls,
            original_device_class=None,
            disabled_by=None, hidden_by=None,
        )

    registry_entities = [
        entry(values["humidifier_entity"]),
        entry(values["fan_entity"]),
        entry(values["led_entity"]),
        entry("switch.ci_alternative_led"),
        entry(values["brightness_entity"]),
        entry(values["temperature_entity"], "temperature"),
        entry(values["humidity_entity"], "humidity"),
    ]
    registry = SimpleNamespace(
        async_get=lambda name: next(
            (item for item in registry_entities if item.entity_id == name),
            None,
        )
    )
    hass = FakeHass(bridge)
    installed = SimpleNamespace(entry_id="ci-venta-config-entry", data=values)
    original = TYPES["HumidifierDehumidifier"]

    async def exercise():
        with (
            patch.object(er, "async_get", return_value=registry),
            patch.object(
                er, "async_entries_for_device", return_value=registry_entities
            ),
        ):
            assert await venta.async_setup(hass, {})
            assert TYPES["HumidifierDehumidifier"] is original
            assert hass.services.registered == []
            assert await venta.async_setup_entry(hass, installed)
            assert TYPES["HumidifierDehumidifier"] is venta._venta_accessory_factory
            assert hass.data[venta.DOMAIN]["config_entry_id"] == installed.entry_id
            assert venta.BRIDGE_ENTRY == bridge.entry_id
            assert hass.executor_calls == 1
            assert len(hass.services.registered) == 2
            assert await venta.async_setup_entry(hass, installed)
            assert hass.executor_calls == 1
            assert len(hass.services.registered) == 2

            # A second UI config entry may not silently rebind the same HAP
            # bridge, even if it chooses the same physical humidifier.
            second = SimpleNamespace(
                entry_id="another-entry", data=dict(values)
            )
            assert not await venta.async_setup_entry(hass, second)
            assert hass.data[venta.DOMAIN]["config_entry_id"] == installed.entry_id

            # A changed, valid LocalTuya LED on the same physical device may
            # not replace an active HAP binding without controlled teardown.
            changed = SimpleNamespace(
                entry_id=installed.entry_id,
                data=dict(values, led_entity="switch.ci_alternative_led"),
            )
            assert not await venta.async_setup_entry(hass, changed)
            assert venta.LED == values["led_entity"]

            # No runtime unload until HomeKit accessory removal is proved safe.
            assert not await venta.async_unload_entry(hass, installed)
            assert hass.executor_calls == 1
            assert hass.scheduled == []

    try:
        asyncio.run(exercise())
    finally:
        TYPES["HumidifierDehumidifier"] = original
    assert TYPES["HumidifierDehumidifier"] is NativeHumidifier
    return {
        "status": "PASS",
        "home_assistant": ha_version,
        "config_entry_setup": "verified",
        "idempotent_replay": True,
        "cross_entry_takeover": "blocked",
        "changed_role_takeover": "blocked",
        "homekit_bridge_recreated": False,
        "device_commands": 0,
        "pairing_events": 0,
        "real_ha_config_writes": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.ha_version), sort_keys=True))
