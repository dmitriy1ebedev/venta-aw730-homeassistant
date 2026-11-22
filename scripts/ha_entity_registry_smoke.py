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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.ha_version), sort_keys=True))
