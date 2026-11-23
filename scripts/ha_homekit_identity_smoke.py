"""P02.2: HA 2026.11.1 / PyHAP AID and IID continuity smoke.

Synthetic data only. Uses actual HA HomeKit classes and persistent allocation
algorithms in a disposable container with --network none. Never starts an HAP
server, loads real .storage, pairs clients, or connects to the air washer.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _hap_ids(accessory):
    """Compute real HA persistent allocation keys; PyHAP has no char.iid."""
    identities = []
    all_iids = []
    storage = accessory.iid_manager._iid_storage
    for service in accessory.services:
        service_iid = storage.get_or_allocate_iid(
            accessory.aid, service.type_id, service.unique_id, None, None,
        )
        characteristics = []
        for char in service.characteristics:
            char_iid = storage.get_or_allocate_iid(
                accessory.aid, service.type_id, service.unique_id,
                char.type_id, char.unique_id,
            )
            characteristics.append((
                str(char.type_id), str(char.unique_id), char_iid,
            ))
            all_iids.append(char_iid)
        identities.append((
            str(service.type_id), str(service.unique_id),
            service_iid, tuple(sorted(characteristics)),
        ))
        all_iids.append(service_iid)
    assert len(all_iids) == len(set(all_iids)), "duplicate accessory IID"
    return tuple(sorted(identities))


def _identity_fingerprint(first: dict) -> str:
    """Digest of synthetic AID/IID and service structure, no pairing values."""
    payload = {
        key: first[key]
        for key in ("venta_aid", "other_aid", "venta_shape", "other_shape")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _read_synthetic_state(path: Path) -> dict:
    """Only read a bounded, non-symlinked synthetic identity fixture."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
        raise ValueError("invalid_synthetic_identity_state")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema") != "venta-synthetic-identity/v1"
        or not isinstance(data.get("fingerprint"), str)
        or len(data["fingerprint"]) != 64
        or not isinstance(data.get("allocations"), dict)
        or set(data["allocations"]) != {"aids", "iids"}
        or not isinstance(data["allocations"]["aids"], dict)
        or not isinstance(data["allocations"]["iids"], dict)
    ):
        raise ValueError("invalid_synthetic_identity_state")
    return data


def validate(
    config_dir: Path, expected_ha_version: str, *,
    state_file: Path | None = None, state_mode: str | None = None,
) -> dict:
    if (state_file is None) != (state_mode is None):
        raise ValueError("identity_state_requires_mode_and_path")
    if state_mode not in (None, "capture", "verify"):
        raise ValueError("invalid_identity_state_mode")
    if state_file is not None and (
        ".storage" in state_file.parts
        or state_file.resolve().is_relative_to(config_dir.resolve())
    ):
        # No code path can write into a real HA configuration or pairing store.
        raise ValueError("identity_state_must_be_outside_ha_config")
    saved_state = (
        _read_synthetic_state(state_file)
        if state_mode == "verify" and state_file is not None else None
    )
    sys.path.insert(0, str(config_dir))
    from homeassistant.const import __version__ as ha_version
    from homeassistant.core import State
    from homeassistant.components.homekit.accessories import (
        TYPES, HomeDriver, get_accessory,
    )
    from homeassistant.components.homekit.aidmanager import AccessoryAidStorage
    from homeassistant.components.homekit.iidmanager import AccessoryIIDStorage
    from homeassistant.components.homekit.type_humidifiers import (
        HumidifierDehumidifier as Native,
    )
    import custom_components.venta_homekit_native as venta

    assert ha_version == expected_ha_version
    assert TYPES.get("HumidifierDehumidifier") is Native
    assert venta._homekit_apis_compatible()

    venta_entity = "humidifier.venta_ci_fake"
    other_entity = "humidifier.another_ci_fake"
    venta.ENTITY = venta_entity
    venta.FAN = "select.venta_ci_fan"
    venta.LED = "switch.venta_ci_led"
    venta.BRIGHTNESS = "select.venta_ci_brightness"
    venta.TEMPERATURE = "sensor.venta_ci_temperature"
    venta.HUMIDITY = "sensor.venta_ci_humidity"
    venta.EXTRA_ENTITIES = (
        venta.FAN, venta.LED, venta.BRIGHTNESS, venta.TEMPERATURE,
    )
    states = {
        venta_entity: State(venta_entity, "off", {
            "friendly_name": "Venta CI",
            "mode": "Manual", "humidity": 56, "current_humidity": 50,
            "min_humidity": 30, "max_humidity": 70,
        }),
        other_entity: State(other_entity, "off", {
            "friendly_name": "Other CI",
            "humidity": 45, "current_humidity": 40,
        }),
        venta.FAN: State(venta.FAN, "3"),
        venta.LED: State(venta.LED, "off"),
        venta.BRIGHTNESS: State(venta.BRIGHTNESS, "5"),
        venta.TEMPERATURE: State(venta.TEMPERATURE, "23.0"),
    }
    fake_hass = SimpleNamespace(states=states)
    fake_registry = SimpleNamespace(async_get=lambda entity_id: None)
    fake_store = SimpleNamespace(async_delay_save=lambda *args: None)

    async def build(allocations=None):
        from homeassistant.components.homekit import aidmanager
        with patch.object(aidmanager.er, "async_get", return_value=fake_registry):
            aids = AccessoryAidStorage(fake_hass, "synthetic-bridge")
        iids = AccessoryIIDStorage(fake_hass, "synthetic-bridge")
        aids.store = fake_store
        iids.store = fake_store
        if allocations is not None:
            aids.allocations = deepcopy(allocations["aids"])
            aids.allocated_aids = set(aids.allocations.values())
            iids.allocations = deepcopy(allocations["iids"])
            iids.allocated_iids = {
                k: sorted(v.values()) for k, v in iids.allocations.items()
            }
        with (
            patch("pyhap.accessory_driver.AsyncZeroconf"),
            patch("pyhap.accessory_driver.AccessoryEncoder"),
            patch("pyhap.accessory_driver.HAPServer"),
            patch("pyhap.accessory_driver.AccessoryDriver.publish"),
            patch("pyhap.accessory_driver.AccessoryDriver.persist"),
        ):
            driver = HomeDriver(
                fake_hass,
                pincode=b"123-45-678",
                entry_id="synthetic-bridge",
                entry_title="Fake bridge",
                bridge_name="Fake bridge",
                iid_storage=iids,
                address="127.0.0.1",
                loop=asyncio.get_running_loop(),
            )
            venda_aid = aids.get_or_allocate_aid_for_entity_id(venta_entity)
            other_aid = aids.get_or_allocate_aid_for_entity_id(other_entity)
            assert venda_aid != other_aid
            venta_accessory = get_accessory(
                fake_hass, driver, states[venta_entity], venda_aid, {},
            )
            other_accessory = get_accessory(
                fake_hass, driver, states[other_entity], other_aid, {},
            )
        assert type(venta_accessory) is venta.VentaEnhancedHumidifier
        assert type(other_accessory) is Native, "other humidifier was modified"
        assert venta_accessory.aid == venda_aid
        assert other_accessory.aid == other_aid
        linked = {
            service.unique_id
            for service in venta_accessory.services if service.unique_id
        }
        required = {
            "venta-fan-v1", "venta-auto-mode-v1",
            "venta-led-v1", "venta-temperature-v1",
        }
        assert required <= linked, (required, linked)
        assert len(linked) == len(set(linked)), "duplicate linked service ids"
        return {
            "venta_aid": venda_aid,
            "other_aid": other_aid,
            "venta_shape": _hap_ids(venta_accessory),
            "other_shape": _hap_ids(other_accessory),
            "allocations": {
                "aids": deepcopy(aids.allocations),
                "iids": deepcopy(iids.allocations),
            },
            "linked_count": len(required),
        }

    saved = TYPES["HumidifierDehumidifier"]
    TYPES["HumidifierDehumidifier"] = venta._venta_accessory_factory
    try:
        async def run():
            first = await build(
                saved_state["allocations"] if saved_state is not None else None
            )
            if saved_state is not None:
                assert _identity_fingerprint(first) == saved_state["fingerprint"], (
                    "cross-process HomeKit AID/IID identity drift"
                )
            # Simulated accessory reload, with the same persisted AID/IID data.
            second = await build(first["allocations"])
            # Simulated Home Assistant restart/update, retaining store data.
            third = await build(second["allocations"])
            for prior, current in ((first, second), (second, third)):
                for name in ("venta_aid", "other_aid", "venta_shape", "other_shape"):
                    assert prior[name] == current[name], (name, "identity drift")
            return first
        first = asyncio.run(run())
    finally:
        TYPES["HumidifierDehumidifier"] = saved

    assert TYPES.get("HumidifierDehumidifier") is Native

    if state_mode == "capture" and state_file is not None:
        # CI runner volume only. Never write to Home Assistant's .storage
        # or read a real pairing file; this is synthetic HAP allocation data.
        state = {
            "schema": "venta-synthetic-identity/v1",
            "allocations": first["allocations"],
            "fingerprint": _identity_fingerprint(first),
        }
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"))
        if len(raw) > 262144:
            raise ValueError("synthetic_identity_state_oversized")
        if state_file.is_symlink() or state_file.exists():
            raise FileExistsError("synthetic_identity_state_must_be_new")
        with state_file.open("x", encoding="utf-8") as output:
            output.write(raw + "\n")

    return {
        "status": "PASS",
        "cross_process_mode": state_mode or "none",
        "cross_process_identity_stable": state_mode == "verify",
        "ha_version": ha_version,
        "native_other_humidifier": True,
        "reload_and_restart_aid_iid_stable": True,
        "linked_service_count": first["linked_count"],
        "pairings_touched": False,
        "physical_device_touched": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", default="2026.11.1")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--state-mode", choices=("capture", "verify"))
    args = parser.parse_args()
    print(json.dumps(validate(
        args.config, args.ha_version,
        state_file=args.state_file, state_mode=args.state_mode,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
