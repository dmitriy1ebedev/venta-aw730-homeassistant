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
from unittest.mock import AsyncMock, PropertyMock, patch


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
            entity("switch.fixture_led_alternative"),
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
                async_entries=lambda domain, *args: [bridge] if domain == "homekit" else []
            ),
        )
        updates: list[tuple[object, dict]] = []
        hass.config_entries.async_update_entry = (
            lambda entry, **kwargs: updates.append((entry, kwargs))
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

                # Real HA ConfigFlow must require an explicit backup and a
                # restart boundary for legacy YAML, without changing the
                # active HomeKit bridge, HAP registry or physical device.
                legacy = {
                    "humidifier_entity": humidifier.entity_id,
                    "bridge_title": bridge.title,
                    "bridge_entry_id": bridge.entry_id,
                    **mapping,
                }
                hass.data["venta_homekit_native"] = {
                    "patched": True, "legacy_yaml": legacy,
                }
                migration = await flow.async_step_user()
                assert migration["step_id"] == "migrate_yaml", migration
                declined = await flow.async_step_migrate_yaml({
                    "confirm_backup": False,
                    "confirm_remove_yaml_and_restart": True,
                })
                assert declined["errors"]["base"] == (
                    "yaml_migration_confirmation_required"
                )
                migrated = await flow.async_step_migrate_yaml({
                    "confirm_backup": True,
                    "confirm_remove_yaml_and_restart": True,
                })
                assert migrated["type"] == "create_entry", migrated
                assert migrated["data"]["bridge_entry_id"] == bridge.entry_id
                assert migrated["data"]["migration_from_yaml"] is True
                assert migrated["data"]["fan_entity"] == mapping["fan_entity"]
                assert hass.data["venta_homekit_native"]["legacy_yaml"] == legacy
                imported = await flow.async_step_import(legacy)
                assert imported["reason"] == (
                    "interactive_yaml_migration_required"
                )

                # Real OptionsFlow API; in-memory staging must not mutate the
                # existing HomeKit bridge or a live LocalTuya mapping.
                from homeassistant.config_entries import OptionsFlow
                from homeassistant.components.repairs import RepairsFlow

                hass.data.pop("venta_homekit_native")
                entry = SimpleNamespace(
                    entry_id="ci-venta-config-entry",
                    domain="venta_homekit_native",
                    unique_id=humidifier.entity_id,
                    data={**legacy, "confirmed_unclassified": []},
                    options={},
                )
                opts = module.VentaConfigFlow.async_get_options_flow(entry)
                assert isinstance(opts, OptionsFlow)
                opts.hass = hass
                with patch.object(
                    type(opts), "config_entry",
                    new_callable=PropertyMock, return_value=entry,
                ):
                    shown = await opts.async_step_init()
                    assert shown["step_id"] == "init", shown
                    staged = await opts.async_step_init({
                        **mapping,
                        "bridge_entry_id": bridge.entry_id,
                        "led_entity": "switch.fixture_led_alternative",
                        "confirm_staging": True,
                    })
                    assert staged["type"] == "create_entry", staged
                    assert staged["data"]["review_proposal"]["led_entity"] == (
                        "switch.fixture_led_alternative"
                    )
                assert entry.data["led_entity"] == "switch.fixture_led"
                assert not updates
                entry.options = staged["data"]

                with (
                    patch.object(flow, "_get_reconfigure_entry", return_value=entry),
                    patch.object(flow, "_abort_if_unique_id_mismatch"),
                ):
                    pending = await flow.async_step_reconfigure()
                    assert pending["step_id"] == "reconfigure", pending
                    rejected = await flow.async_step_reconfigure({
                        "confirm_backup": True,
                        "confirm_manual_restart": False,
                    })
                    assert rejected["errors"]["base"] == (
                        "restart_confirmation_required"
                    )
                    assert not updates
                    approved = await flow.async_step_reconfigure({
                        "confirm_backup": True,
                        "confirm_manual_restart": True,
                    })
                    assert approved["reason"] == (
                        "restart_required_for_reconfigure"
                    )
                assert len(updates) == 1, updates
                assert updates[0][1]["data"]["led_entity"] == (
                    "switch.fixture_led_alternative"
                )
                assert "review_proposal" not in updates[0][1]["options"]
                assert not hass.data
                assert bridge.entry_id == "fixture-homekit-bridge"

                # The genuine HA RepairsFlow class revalidates the original
                # entry but does not reload the bridge, change credentials,
                # perform pairing, or call services.
                repair_spec = importlib.util.spec_from_file_location(
                    pkgname + ".repairs", component / "repairs.py"
                )
                assert repair_spec and repair_spec.loader
                repair_module = importlib.util.module_from_spec(repair_spec)
                repair_spec.loader.exec_module(repair_module)
                hass.config_entries.async_get_entry = lambda identifier: (
                    entry if identifier == entry.entry_id else None
                )
                repair = await repair_module.async_create_fix_flow(
                    hass, "binding_" + entry.entry_id,
                    {"entry_id": entry.entry_id},
                )
                assert isinstance(repair, RepairsFlow)
                repair.hass = hass
                check = await repair.async_step_init()
                assert check["step_id"] == "init", check
                done = await repair.async_step_init({"confirm_review": True})
                assert done["type"] == "create_entry", done
                assert len(updates) == 1
                assert not hass.data

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
