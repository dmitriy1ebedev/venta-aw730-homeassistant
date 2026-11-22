"""Offline compatibility smoke using REAL HA 2026.11.1 and PyHAP classes.

Run only in a disposable GitHub Actions HA container with --network none and
a synthetic config. This never starts a HomeKit server, creates a pairing,
connects to Tuya, or writes Home Assistant storage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


class MemoryCharacteristic:
    def __init__(self) -> None:
        self.value = None

    def set_value(self, value: object) -> None:
        self.value = value


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bool]] = []

    async def async_call(self, domain, action, data, blocking=False):
        self.calls.append((domain, action, dict(data), blocking))


class FakeHass:
    def __init__(self, entity_id, state) -> None:
        self.states = {entity_id: state}
        self.services = FakeServices()
        self.tasks = []

    def async_create_task(self, coro) -> None:
        self.tasks.append(asyncio.create_task(coro))

    async def drain(self) -> None:
        tasks, self.tasks = self.tasks, []
        await asyncio.gather(*tasks)


def validate(config_dir: Path, expected_ha_version: str) -> dict:
    """Verify real HA/PyHAP imports, clamping, commands and identity contracts."""
    if not (config_dir / "custom_components/venta_homekit_native/manifest.json").is_file():
        raise AssertionError("staged Venta integration missing")
    sys.path.insert(0, str(config_dir))

    from homeassistant.const import __version__ as ha_version
    from homeassistant.core import State
    from homeassistant.components.homekit.accessories import TYPES
    from homeassistant.components.homekit.type_humidifiers import (
        HumidifierDehumidifier as NativeHumidifier,
    )
    from pyhap.characteristic import Characteristic
    from pyhap.service import Service
    import custom_components.venta_homekit_native as venta

    assert ha_version == expected_ha_version, (ha_version, expected_ha_version)
    assert venta.DOMAIN == "venta_homekit_native"
    assert TYPES.get("HumidifierDehumidifier") is NativeHumidifier, "HomeKit registry unexpectedly patched"
    assert issubclass(venta.VentaEnhancedHumidifier, NativeHumidifier)
    assert hasattr(Characteristic, "override_properties"), "PyHAP characteristic API drift"
    assert hasattr(Service, "add_linked_service"), "PyHAP linked-service API drift"

    entity = "humidifier.venta_ci_fake"
    venta.ENTITY = entity
    fake = FakeHass(entity, State(entity, "on", {
        "min_humidity": 30,
        "max_humidity": 70,
        "humidity": 55,
        "current_humidity": 50,
        "mode": "Manual",
    }))
    accessory = venta.VentaEnhancedHumidifier.__new__(venta.VentaEnhancedHumidifier)
    accessory.hass = fake
    accessory.entity_id = entity
    accessory._hk_device_class = 1
    accessory._target_humidity_char_name = "RelativeHumidityHumidifierThreshold"
    accessory.char_target_humidity = MemoryCharacteristic()
    accessory.char_target_humidifier_dehumidifier = MemoryCharacteristic()
    history = []
    accessory.async_call_service = lambda *args: history.append(args)

    # This calls the real installed HA NativeHumidifier._set_chars via super(),
    # not a hand-written approximation of HA range/command behavior.
    for requested, expected in ((5, 30), (45, 45), (95, 70)):
        history.clear()
        accessory._set_chars({"RelativeHumidityHumidifierThreshold": requested})
        assert history, (requested, "native HA emitted no command")
        domain, service, data, _reason = history[-1]
        assert (domain, service) == ("humidifier", "set_humidity"), history
        assert data["entity_id"] == entity, history
        assert data["humidity"] == expected, (requested, expected, data)
        if requested != expected:
            assert accessory.char_target_humidity.value == expected

    history.clear()
    accessory._set_chars({"TargetHumidifierDehumidifierState": 2})
    assert not history, "invalid dehumidifier command was forwarded"
    assert not fake.tasks, "invalid mode scheduled a task"

    async def verify_real_ha_command_dispatch():
        accessory._set_chars({"TargetHumidifierDehumidifierState": 0})
        await fake.drain()
        assert fake.services.calls[-1][:2] == ("humidifier", "set_mode")
        assert fake.services.calls[-1][2]["mode"] == "Auto"
        assert accessory.char_target_humidifier_dehumidifier.value == 0

    asyncio.run(verify_real_ha_command_dispatch())
    assert TYPES.get("HumidifierDehumidifier") is NativeHumidifier, "global HomeKit registry changed"
    return {
        "status": "PASS",
        "home_assistant": ha_version,
        "real_homekit_base": NativeHumidifier.__name__,
        "real_pyhap_types": True,
        "tests": ["imports", "TYPES_identity", "humidity_30_45_70", "invalid_mode", "Auto_dispatch"],
        "synthetic_entity_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", default="2026.11.1")
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.ha_version), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
