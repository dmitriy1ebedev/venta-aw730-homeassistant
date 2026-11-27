"""P03.2: exercise real HA entity_registry symbols with synthetic fixtures.

No Home Assistant instance, network access, config writes or pairing. This runs
inside a disposable, --network none Home Assistant container in GitHub CI.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def validate(config: Path, expected_version: str) -> dict:
    from homeassistant.const import __version__ as ha_version
    from homeassistant.helpers import entity_registry as er

    assert ha_version == expected_version, "wrong HA version"
    assert callable(er.async_get)
    assert callable(er.async_entries_for_device)

    file = config / "custom_components" / "venta_homekit_native" / "entity_discovery.py"
    spec = importlib.util.spec_from_file_location("venta_discovery_ci", file)
    assert spec and spec.loader
    discovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discovery)

    def fake(entity_id, device="ci-dev-one", klass=None):
        return SimpleNamespace(
            entity_id=entity_id,
            device_id=device,
            config_entry_id="ci-localtuya-entry",
            platform="localtuya",
            device_class=klass,
            original_device_class=None,
            disabled_by=None,
            hidden_by=None,
        )

    base = fake("humidifier.ci_venta")
    rows = [
        base,
        fake("select.ci_fan"),
        fake("select.ci_brightness"),
        fake("switch.ci_led"),
        fake("sensor.ci_temperature", klass="temperature"),
        fake("sensor.ci_humidity", klass="humidity"),
        fake("switch.ci_foreign_led", device="ci-dev-two"),
    ]
    choices = {
        "fan": "select.ci_fan",
        "led": "switch.ci_led",
        "brightness": "select.ci_brightness",
        "temperature": "sensor.ci_temperature",
        "humidity": "sensor.ci_humidity",
    }
    registry = SimpleNamespace(async_get=lambda entity_id: base if entity_id == base.entity_id else None)
    mock_hass = object()
    with (
        patch.object(er, "async_get", return_value=registry),
        patch.object(er, "async_entries_for_device", return_value=rows),
    ):
        plan = discovery.discover_from_hass(mock_hass, base.entity_id)
        assert plan["status"] == "review_required"
        assert plan["read_only"]
        assert not any(
            "ci_foreign" in value
            for role in plan["roles"].values() for value in role["options"]
        )
        assert discovery.validate_from_hass(mock_hass, base.entity_id, choices) == {}
        invalid = dict(choices, led="switch.ci_foreign_led")
        errors = discovery.validate_from_hass(mock_hass, base.entity_id, invalid)
        assert errors.get("led") == "different_or_disabled_device"
        assert plan["roles"]["fan"]["suggested"] is None
        assert plan["roles"]["brightness"]["suggested"] is None
    return {
        "status": "PASS",
        "home_assistant": ha_version,
        "official_registry_api": True,
        "cross_device_selection_rejected": True,
        "manual_review_required": True,
        "service_calls": 0,
        "device_commands": 0,
    }


def validate_device_registry(config: Path) -> dict:
    """Exercise the actual HA registries across two independently loaded stores."""
    import asyncio
    import tempfile
    from datetime import datetime, timezone

    from homeassistant import bootstrap, config_entries, loader
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    component = config / "custom_components" / "venta_homekit_native" / "device_binding.py"
    spec = importlib.util.spec_from_file_location("venta_device_binding_ci", component)
    assert spec and spec.loader
    binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding)

    def fixture_entry(entry_id, domain):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "created_at": now, "modified_at": now, "data": {},
            "discovery_keys": {}, "disabled_by": None, "domain": domain,
            "entry_id": entry_id, "minor_version": 1, "options": {},
            "pref_disable_new_entities": False, "pref_disable_polling": False,
            "source": "user", "subentries": [], "title": domain,
            "unique_id": None, "version": 1,
        }

    async def exercise(root: Path, previous=None):
        hass = HomeAssistant(str(root))
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await loader.async_get_custom_components(hass)
        assert await bootstrap.async_load_base_functionality(hass)
        registry, entities = dr.async_get(hass), er.async_get(hass)
        source_entry = hass.config_entries.async_get_entry("ci-localtuya")
        venta = hass.config_entries.async_get_entry("ci-venta")
        neighbor_entry = hass.config_entries.async_get_entry("ci-neighbor")
        assert source_entry and venta and neighbor_entry
        try:
            if previous is None:
                source = registry.async_get_or_create(
                    config_entry_id=source_entry.entry_id,
                    identifiers={("localtuya", "synthetic-source")},
                    name="CI source",
                )
                neighbor = registry.async_get_or_create(
                    config_entry_id=neighbor_entry.entry_id,
                    identifiers={("mqtt", "synthetic-neighbor")},
                    name="CI neighbor",
                )
                humidifier = entities.async_get_or_create(
                    "humidifier", "localtuya", "synthetic-humidifier",
                    config_entry=source_entry, device_id=source.id,
                    suggested_object_id="venta_ci_source",
                )
                led = entities.async_get_or_create(
                    "switch", "localtuya", "synthetic-led",
                    config_entry=source_entry, device_id=source.id,
                    suggested_object_id="venta_ci_led",
                )
                unrelated = entities.async_get_or_create(
                    "sensor", "mqtt", "synthetic-neighbor",
                    config_entry=neighbor_entry, device_id=neighbor.id,
                    suggested_object_id="venta_ci_neighbor",
                )
            else:
                source = registry.async_get(previous["source"])
                neighbor = registry.async_get(previous["neighbor"])
                humidifier = entities.async_get(previous["humidifier"])
                led = entities.async_get(previous["led"])
                unrelated = entities.async_get(previous["unrelated"])
                assert all(item is not None for item in (source, neighbor, humidifier, led, unrelated))
                assert venta.data.get(binding.PIN_FIELD) == previous["identity"]
            source_before, neighbor_before = source, neighbor
            original_entities = {item.entity_id: item for item in (humidifier, led, unrelated)}
            identity, card = binding.register_logical_device(hass, venta, humidifier.entity_id)
            assert binding.register_logical_device(hass, venta, humidifier.entity_id) == (identity, card)
            assert registry.async_get(card).config_entry_id == venta.entry_id
            assert card != source.id and card != neighbor.id
            assert len(dr.async_entries_for_config_entry(registry, venta.entry_id)) == 1
            assert registry.async_get(source.id) == source_before
            assert registry.async_get(neighbor.id) == neighbor_before
            assert all(entities.async_get(key) == value for key, value in original_entities.items())
            result = {
                "source": source.id, "neighbor": neighbor.id, "card": card,
                "humidifier": humidifier.entity_id, "led": led.entity_id,
                "unrelated": unrelated.entity_id, "identity": identity,
            }
            if previous is not None:
                assert result == previous, "registry identity changed across reload"
                # A different valid LocalTuya humidifier is never accepted as
                # a replacement, even on the same physical registry device.
                replacement = entities.async_get_or_create(
                    "humidifier", "localtuya", "synthetic-replacement",
                    config_entry=source_entry, device_id=source.id,
                    suggested_object_id="venta_ci_replacement",
                )
                for entity_id, reason in (
                    (replacement.entity_id, "source_identity_changed"),
                    ("humidifier.missing_ci_source", "source_missing"),
                ):
                    try:
                        binding.register_logical_device(hass, venta, entity_id)
                    except binding.BindingError as exc:
                        assert str(exc) == reason
                    else:
                        raise AssertionError("changed/missing binding accepted")
                assert len(dr.async_entries_for_config_entry(registry, venta.entry_id)) == 1
                assert venta.data[binding.PIN_FIELD] == identity
                assert registry.async_get(card).id == card
            return result
        finally:
            await hass.async_stop(force=True)

    with tempfile.TemporaryDirectory(prefix="venta-ci-device-registry-") as tmp:
        root = Path(tmp)
        storage = root / ".storage"
        storage.mkdir()
        (storage / "core.config_entries").write_text(json.dumps({
            "version": 1, "minor_version": 5, "key": "core.config_entries",
            "data": {"entries": [
                fixture_entry("ci-localtuya", "localtuya"),
                fixture_entry("ci-venta", binding.DOMAIN),
                fixture_entry("ci-neighbor", "mqtt"),
            ]},
        }), encoding="utf-8")
        captured = asyncio.run(exercise(root))
        assert (storage / "core.device_registry").is_file()
        assert (storage / "core.entity_registry").is_file()
        assert asyncio.run(exercise(root, captured)) == captured
    return {
        "real_device_registry": True, "separate_device": True,
        "real_entity_registry": True, "stable_across_storage_reload": True,
        "original_registry_entries_unchanged": True, "replacement_rejected": True,
        "physical_device_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", required=True)
    args = parser.parse_args()
    result = validate(args.config, args.ha_version)
    result["native_device"] = validate_device_registry(args.config)
    print(json.dumps(result, sort_keys=True))
