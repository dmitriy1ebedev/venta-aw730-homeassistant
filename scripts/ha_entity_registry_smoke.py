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


def validate_native_platforms(config: Path, browser_fixture: Path | None = None) -> dict:
    """Actual HA entity platforms + service dispatch; synthetic LocalTuya only."""
    import asyncio
    import shutil
    import sys
    import tempfile
    from datetime import datetime, timezone

    from homeassistant import bootstrap, config_entries, loader, setup
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    def fixture_entry(entry_id, domain, *, options=None, disabled_by=None):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "created_at": now, "modified_at": now, "data": {},
            "discovery_keys": {}, "disabled_by": disabled_by, "domain": domain,
            "entry_id": entry_id, "minor_version": 1, "options": options or {},
            "pref_disable_new_entities": False, "pref_disable_polling": False,
            "source": "user", "subentries": [], "title": domain,
            "unique_id": None, "version": 1,
        }

    async def exercise(root: Path):
        hass = HomeAssistant(str(root))
        hass.config.skip_pip = True
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await loader.async_get_custom_components(hass)
        assert await bootstrap.async_load_base_functionality(hass)
        devices, registry = dr.async_get(hass), er.async_get(hass)
        source = hass.config_entries.async_get_entry("ci-localtuya")
        entry = hass.config_entries.async_get_entry("ci-venta")
        bridge = hass.config_entries.async_get_entry("ci-homekit")
        assert source and entry and bridge
        sys.path.insert(0, str(root))
        import custom_components.venta_homekit_native as venta
        from custom_components.venta_homekit_native.native_sensor_values import sensor_fingerprint

        calls = []
        roles = {}
        original_registry = {}
        try:
            physical = devices.async_get_or_create(
                config_entry_id=source.entry_id,
                identifiers={("localtuya", "ci-synthetic-physical")},
                name="Synthetic LocalTuya washer",
            )
            specifications = {
                "humidifier": ("humidifier", "off", {"humidity": 45, "mode": "Auto",
                    "available_modes": ["Auto", "Manual", "Sleep"]}),
                "fan": ("select", "1", {"options": ["1", "2", "3", "4", "5"]}),
                "led": ("switch", "off", {}),
                "brightness": ("select", "1", {"options": [str(i) for i in range(1, 9)]}),
                "temperature": ("sensor", "22", {"device_class": "temperature",
                    "unit_of_measurement": "\N{DEGREE SIGN}C"}),
                "humidity": ("sensor", "48", {"device_class": "humidity", "unit_of_measurement": "%"}),
                "pm25": ("sensor", "12", {"device_class": "pm25",
                    "unit_of_measurement": "\N{MICRO SIGN}g/m\N{SUPERSCRIPT THREE}"}),
                "water_level": ("sensor", "82", {"unit_of_measurement": "%"}),
                "filter_days": ("sensor", "20", {"device_class": "duration", "unit_of_measurement": "d"}),
                "cleaning_days": ("sensor", "7", {"device_class": "duration", "unit_of_measurement": "d"}),
                "service_days": ("sensor", "90", {"device_class": "duration", "unit_of_measurement": "d"}),
            }
            for domain in ("humidifier", "fan", "light", "sensor", "switch", "select"):
                assert await setup.async_setup_component(hass, domain, {})
            for role, (domain, state, attrs) in specifications.items():
                row = registry.async_get_or_create(
                    domain, "localtuya", "ci-" + role,
                    config_entry=source, device_id=physical.id,
                    suggested_object_id="ci_source_" + role,
                    original_device_class=attrs.get("device_class"),
                )
                roles[role] = row.entity_id
                original_registry[row.entity_id] = row
                hass.states.async_set(row.entity_id, state, attrs)
            core_roles = ("humidifier", "fan", "led", "brightness", "temperature", "humidity")
            values = {role + "_entity": roles[role] for role in core_roles}
            values.update(bridge_title="homekit", bridge_entry_id=bridge.entry_id, confirmed_unclassified=[])
            hass.config_entries.async_update_entry(bridge, options={
                "mode": "bridge", "filter": {"include_entities": [roles["humidifier"]]},
            })
            hass.config_entries.async_update_entry(entry, data=values, options={"native_device_ui": True})
            from custom_components.venta_homekit_native.device_binding import resolve_source
            identity = resolve_source(hass, roles["humidifier"])
            configured = {role: roles[role] for role in roles if role not in core_roles}
            pins = {role: sensor_fingerprint(
                registry.async_get(roles["humidifier"]), registry.async_get(entity_id), role, identity)
                for role, entity_id in configured.items()}
            hass.config_entries.async_update_entry(entry, options={
                "native_device_ui": True, "native_sensor_entities": configured,
                "native_sensor_pins": pins,
            })

            # HAP lifecycle has its own real-HA smoke. Stub only that legacy
            # side effect here, and exercise the real Venta setup entry and
            # the real HA platform-forwarding / registration machinery.
            async def no_hap_setup(instance, _config):
                instance.data[venta.DOMAIN] = {"patched": True}
                return True

            # HA setup.py marks the top-level component loaded BEFORE it
            # enters the config-entry setup lock, specifically to prevent
            # forwarding from recursively setting up the same entry. We
            # reproduce that lifecycle step for the stubbed HAP owner only.
            hass.config.components.add(venta.DOMAIN)
            print("native platform fixture: forwarding", flush=True)
            async with asyncio.timeout(45):
                with patch.object(venta, "async_setup", no_hap_setup):
                    async with entry.setup_lock:
                        assert await venta.async_setup_entry(hass, entry)
                await hass.async_block_till_done()
            print("native platform fixture: forwarded", flush=True)
            active = hass.data[venta.DOMAIN]
            assert active.get("native_ui_platforms_loaded"), "native platforms did not load"
            card = devices.async_get(active["native_device"]["device_id"])
            assert card.id != physical.id and card.config_entry_id == entry.entry_id
            projections = {row.unique_id.rsplit("-", 1)[-1]: row
                           for row in er.async_entries_for_config_entry(registry, entry.entry_id)}
            expected = {"native_humidifier", "native_fan", "native_led",
                        *("native_" + role for role in ("temperature", "humidity", *configured))}
            assert set(projections) == expected, f"native entity roster mismatch: {sorted(projections)} != {sorted(expected)}"
            assert all(row.device_id == card.id for row in projections.values())
            assert all(registry.async_get(key) == row for key, row in original_registry.items())

            def native_state(role):
                return hass.states.get(projections["native_" + role].entity_id)

            for role in expected:
                state = hass.states.get(projections[role].entity_id)
                assert state is not None and state.state not in ("unknown", "unavailable"), role

            if browser_fixture is not None:
                # Export only the verified synthetic fixture. No live HA
                # storage, authentication or user data is accessible here.
                capture = {
                    "device_id": card.id,
                    "entities": {role: row.entity_id for role, row in projections.items()},
                    "states": {entity_id: {"state": hass.states.get(entity_id).state,
                        "attributes": dict(hass.states.get(entity_id).attributes)}
                        for entity_id in (*roles.values(), *(row.entity_id for row in projections.values()))},
                }
                (root / "native-browser-states.json").write_text(json.dumps(capture), encoding="utf-8")

            # Use HA's native service registry for the OUTER call. Intercept
            # only the exact synthetic LocalTuya IDs for source readback.
            original_call = type(hass.services).async_call

            async def source_call(service_registry, domain, service, service_data=None, **kwargs):
                target = (service_data or {}).get("entity_id")
                if isinstance(target, str) and target in roles.values():
                    role = next(key for key, value in roles.items() if value == target)
                    current = hass.states.get(target)
                    state, attrs = current.state, dict(current.attributes)
                    calls.append((role, domain, service))
                    if service == "turn_on":
                        state = "on"
                    elif service == "turn_off":
                        state = "off"
                    elif service == "set_humidity":
                        attrs["humidity"] = service_data["humidity"]
                    elif service == "set_mode":
                        attrs["mode"] = service_data["mode"]
                    elif service == "select_option":
                        state = service_data["option"]
                    else:
                        raise AssertionError("unexpected synthetic source service")
                    hass.states.async_set(target, state, attrs, context=kwargs.get("context"))
                    return None
                return await original_call(service_registry, domain, service, service_data, **kwargs)

            async def dispatch(role, domain, service, **data):
                await hass.services.async_call(domain, service,
                    {"entity_id": projections["native_" + role].entity_id, **data}, blocking=True)
                await hass.async_block_till_done()

            with patch.object(type(hass.services), "async_call", source_call):
                await dispatch("humidifier", "humidifier", "turn_on")
                await dispatch("humidifier", "humidifier", "set_humidity", humidity=60)
                assert native_state("humidifier").attributes["humidity"] == 60
                await dispatch("humidifier", "humidifier", "set_mode", mode="Sleep")
                assert native_state("humidifier").attributes["mode"] == "Sleep"
                await dispatch("fan", "fan", "set_percentage", percentage=80)
                assert native_state("fan").attributes["percentage"] == 80
                assert native_state("humidifier").attributes["mode"] == "Manual"
                await dispatch("led", "light", "turn_on", brightness=255)
                assert native_state("led").attributes["brightness"] == 255
                await dispatch("led", "light", "turn_off")
                assert native_state("led").state == "off"
                before = len(calls)
                # A live change in HomeKit export options must immediately
                # make Venta projections unavailable, without changing the
                # original registry or dispatching a hardware command.
                safe_options = dict(bridge.options)
                hass.config_entries.async_update_entry(bridge, options={"filter": {}})
                await hass.async_block_till_done()
                assert all(hass.states.get(row.entity_id).state == "unavailable" for row in projections.values())
                from homeassistant.exceptions import HomeAssistantError
                try:
                    await dispatch("humidifier", "humidifier", "turn_off")
                except HomeAssistantError:
                    pass
                else:
                    raise AssertionError("unsafe export command accepted")
                assert len(calls) == before
                hass.config_entries.async_update_entry(bridge, options=safe_options)
                await hass.async_block_till_done()
                assert native_state("humidifier").state == "on"
                hass.states.async_set(roles["pm25"], "unavailable")
                await hass.async_block_till_done()
                assert native_state("pm25").state == "unavailable"
                hass.states.async_set(roles["humidifier"], "unavailable")
                await hass.async_block_till_done()
                assert native_state("humidifier").state == "unavailable"
                assert native_state("water_level").state == "unavailable"
                assert len(calls) == before
            assert calls == [
                ("humidifier", "humidifier", "turn_on"),
                ("humidifier", "humidifier", "set_humidity"),
                ("humidifier", "humidifier", "set_mode"),
                ("humidifier", "humidifier", "set_mode"),
                ("fan", "select", "select_option"),
                ("led", "switch", "turn_on"),
                ("brightness", "select", "select_option"),
                ("led", "switch", "turn_off"),
            ]
            return {"real_platform_entities": len(projections), "native_service_dispatch": True,
                    "source_registry_unchanged": True, "unavailable_propagates": True,
                    "synthetic_service_calls": len(calls), "physical_device_calls": 0,
                    "runtime_export_guard": True}
        finally:
            await hass.async_stop(force=True)
            sys.path.remove(str(root))

    with tempfile.TemporaryDirectory(prefix="venta-ci-native-platforms-") as tmp:
        root = Path(tmp)
        shutil.copytree(config / "custom_components", root / "custom_components")
        storage = root / ".storage"
        storage.mkdir()
        (storage / "core.config_entries").write_text(json.dumps({
            "version": 1, "minor_version": 5, "key": "core.config_entries",
            "data": {"entries": [
                fixture_entry("ci-localtuya", "localtuya"),
                fixture_entry("ci-venta", "venta_homekit_native"),
                fixture_entry("ci-homekit", "homekit", disabled_by="user"),
            ]},
        }), encoding="utf-8")
        result = asyncio.run(asyncio.wait_for(exercise(root), timeout=120))
        if browser_fixture is not None:
            capture = json.loads((root / "native-browser-states.json").read_text())
            capture["storage"] = {name: json.loads((storage / name).read_text())
                for name in ("core.device_registry", "core.entity_registry", "core.config_entries")}
            assert {row["entry_id"] for row in capture["storage"]["core.config_entries"]["data"]["entries"]} == {
                "ci-localtuya", "ci-venta", "ci-homekit"}
            assert len(capture["entities"]) == 10
            browser_fixture.write_text(json.dumps(capture), encoding="utf-8")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ha-version", required=True)
    parser.add_argument("--browser-fixture", type=Path)
    args = parser.parse_args()
    result = validate(args.config, args.ha_version)
    result["native_device"] = validate_device_registry(args.config)
    result["native_platforms"] = validate_native_platforms(args.config, args.browser_fixture)
    print(json.dumps(result, sort_keys=True))
