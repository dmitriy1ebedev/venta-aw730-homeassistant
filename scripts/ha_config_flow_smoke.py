"""Exercise Venta's config-flow UI using the *real* Home Assistant ConfigFlow.

Only synthetic registry entries and HomeKit config-entry metadata are used.
No Home Assistant instance, LAN access, service calls, pairing or config writes.
Runs in disposable network-disabled HA 2026.11.x containers in CI.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def validate(config: Path, expected_version: str) -> dict:
    from homeassistant.config_entries import ConfigFlow
    from homeassistant.const import __version__ as ha_version
    from homeassistant.helpers import entity_registry as er

    assert ha_version == expected_version, "wrong HA version"
    component = config / "custom_components" / "venta_homekit_native"
    assert (component / "config_flow.py").is_file()

    # Preserve the real HA ConfigFlow and registry APIs but don't load the
    # integration's YAML/HomeKit setup or any real state from disk.
    pkgname = "venta_ci_flow"
    package = types.ModuleType(pkgname)
    package.__path__ = [str(component)]
    package.DOMAIN = "venta_homekit_native"
    with patch.dict(sys.modules, {pkgname: package}):
        spec = importlib.util.spec_from_file_location(
            pkgname + ".config_flow", component / "config_flow.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        flow = module.VentaConfigFlow()
        assert isinstance(flow, ConfigFlow)

        def entity(name, device="fixture-device", klass=None):
            return SimpleNamespace(
                entity_id=name, device_id=device,
                config_entry_id="fixture-localtuya-entry",
                platform="localtuya", device_class=klass,
                original_device_class=None,
                disabled_by=None, hidden_by=None,
            )

        humidifier = entity("humidifier.fixture_venta")
        rows = [
            humidifier,
            entity("select.fixture_fan"),
            entity("select.fixture_brightness"),
            entity("switch.fixture_led"),
            entity("sensor.fixture_temperature", klass="temperature"),
            entity("sensor.fixture_humidity", klass="humidity"),
        ]
        registry = SimpleNamespace(
            entities={item.entity_id: item for item in rows},
            async_get=lambda name: next(
                (item for item in rows if item.entity_id == name), None
            ),
        )
        bridge = SimpleNamespace(
            entry_id="fixture-homekit-bridge",
            title="Synthetic HomeKit Bridge",
            options={
                "mode": "bridge",
                "filter": {"include_entities": ["humidifier.fixture_venta"]},
            },
        )
        hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(
                async_entries=lambda domain: [bridge] if domain == "homekit" else []
            ),
        )
        flow.hass = hass

        mapping = {
            "fan_entity": "select.fixture_fan",
            "led_entity": "switch.fixture_led",
            "brightness_entity": "select.fixture_brightness",
            "temperature_entity": "sensor.fixture_temperature",
            "humidity_entity": "sensor.fixture_humidity",
        }

        async def exercise() -> None:
            with (
                patch.object(er, "async_get", return_value=registry),
                patch.object(er, "async_entries_for_device", return_value=rows),
                patch.object(flow, "async_set_unique_id", new_callable=AsyncMock),
                patch.object(flow, "_abort_if_unique_id_configured"),
            ):
                opening = await flow.async_step_user()
                assert opening["type"] == "form", opening
                assert opening["step_id"] == "user"
                wrong = await flow.async_step_user({
                    "humidifier_entity": "humidifier.not_localtuya",
                    "bridge_entry_id": "fixture-homekit-bridge",
                })
                assert wrong["errors"].get("humidifier_entity") == "invalid_humidifier"
                chosen = await flow.async_step_user({
                    "humidifier_entity": humidifier.entity_id,
                    "bridge_entry_id": bridge.entry_id,
                })
                assert chosen["step_id"] == "entities", chosen
                incorrect = await flow.async_step_entities({
                    **mapping, "led_entity": "switch.other_device"
                })
                assert incorrect["errors"].get("led_entity") == "invalid_entity"
                created = await flow.async_step_entities(mapping)
                assert created["type"] == "create_entry", created
                assert created["data"]["bridge_entry_id"] == bridge.entry_id
                assert created["data"]["led_entity"] == mapping["led_entity"]
                assert created["data"]["confirmed_unclassified"] == []

        asyncio.run(exercise())

    return {
        "status": "PASS",
        "home_assistant": ha_version,
        "real_configflow_base": True,
        "synthetic_registry": True,
        "real_device_commands": 0,
        "real_pairing_changes": 0,
        "writes": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.ha_version), sort_keys=True))
