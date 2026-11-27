"""Read-only, privacy-safe diagnostics for a YAML-configured Venta integration.

Only allow-listed statuses and semver values leave this module. Never report
entity IDs, attributes, keys, network identifiers, or HomeKit pairing data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_STATUS = {"on", "off", "unavailable", "unknown"}
_LINKED = ("fan", "led", "brightness", "temperature", "humidity")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def _safe_version(value: Any) -> str:
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else "unknown"


def _manifest_version(path: Path) -> str:
    """Read only version from a local manifest; never copy arbitrary JSON values."""
    if path.is_symlink() or not path.is_file():
        return "unknown"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "unknown"
    return _safe_version(data.get("version")) if isinstance(data, dict) else "unknown"


def _entity_status(states: Any, entity_id: Any, *, is_device: bool = False) -> str:
    if not isinstance(entity_id, str) or not entity_id.strip():
        return "not_configured"
    try:
        item = states.get(entity_id)
    except (AttributeError, KeyError, TypeError):
        return "unknown"
    if item is None:
        return "missing"
    value = getattr(item, "state", None)
    if is_device:
        return value if value in _STATUS else "other"
    return "unavailable" if value in ("unavailable", "unknown") else "available"


def _localtuya_status(entries: Any) -> str:
    if entries is None:
        return "unknown"
    if not entries:
        return "not_configured"
    if any(getattr(getattr(entry, "state", None), "value", None) == "loaded"
           or getattr(entry, "state", None) == "loaded" for entry in entries):
        return "loaded"
    return "not_loaded"


def _bridge_status(hass: Any, entry_id: Any) -> str:
    if not isinstance(entry_id, str) or not entry_id.strip():
        return "not_configured"
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
    except (AttributeError, KeyError, TypeError):
        return "unknown"
    if entry is None:
        return "not_found"
    runtime = getattr(entry, "runtime_data", None)
    homekit = getattr(runtime, "homekit", None)
    if homekit is None:
        return "not_ready"
    ready = (
        getattr(homekit, "status", None) == "running"
        and getattr(homekit, "driver", None) is not None
        and getattr(homekit, "bridge", None) is not None
    )
    return "ready" if ready else "not_ready"


def native_ui_status(hass: Any) -> dict[str, Any]:
    """Bounded status only; no registry identifiers or raw sensor values."""
    result = {"device_registered": False, "platforms_loaded": False,
              "control_status": "not_configured", "sensor_count": 0}
    try:
        active = getattr(hass, "data", {}).get("venta_homekit_native", {})
        result["device_registered"] = bool(active.get("native_device"))
        result["platforms_loaded"] = active.get("native_ui_platforms_loaded") is True
        controller = active.get("native_control")
        if controller is None:
            return result
        if not result["platforms_loaded"]:
            result["control_status"] = "not_enabled"
        elif controller.admission is None or not controller.admission():
            result["control_status"] = "review_exports"
        else:
            from .native_control import ControlError
            try:
                controller.state("humidifier")
            except ControlError:
                result["control_status"] = "source_unavailable"
            else:
                result["control_status"] = "ready"
        sensors = active.get("native_sensors")
        if sensors is not None:
            result["sensor_count"] = 2 + sum(
                role in sensors.roles for role in ("pm25", "water_level", "filter_days", "cleaning_days", "service_days"))
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        result["control_status"] = "unknown"
    return result


def collect_diagnostics(
    hass: Any,
    *,
    entity_ids: dict[str, Any],
    bridge_entry_id: str | None,
    home_assistant_version: str,
    integration_dir: Path,
) -> dict[str, Any]:
    """Return strict allow-listed schema; never include an entity ID or raw state."""
    required = ("humidifier",) + _LINKED
    config_state = "complete" if all(
        isinstance(entity_ids.get(k), str) and entity_ids[k].strip()
        for k in required
    ) and isinstance(bridge_entry_id, str) and bridge_entry_id.strip() else "incomplete"
    try:
        entries = hass.config_entries.async_entries("localtuya")
    except (AttributeError, KeyError, TypeError):
        entries = None
    localtuya = _localtuya_status(entries)
    config_dir = getattr(getattr(hass, "config", None), "config_dir", None)
    if isinstance(config_dir, str) and config_dir:
        localtuya_version = _manifest_version(
            Path(config_dir) / "custom_components" / "localtuya" / "manifest.json"
        )
    else:
        localtuya_version = "unknown"
    humidifier = _entity_status(
        hass.states, entity_ids.get("humidifier"), is_device=True
    )
    linked = {key: _entity_status(hass.states, entity_ids.get(key)) for key in _LINKED}
    bridge = _bridge_status(hass, bridge_entry_id)

    if config_state != "complete":
        recommendation = "review_venta_configuration"
    elif localtuya == "not_configured":
        recommendation = "check_localtuya_configuration"
    elif localtuya == "not_loaded":
        recommendation = "check_localtuya_load_state"
    elif humidifier in ("unavailable", "unknown", "missing"):
        recommendation = "check_localtuya_connection_logs"
    elif bridge != "ready":
        recommendation = "check_existing_homekit_bridge"
    elif any(value != "available" for value in linked.values()):
        recommendation = "check_missing_linked_entities"
    else:
        recommendation = "none"

    return {
        "schema": 1,
        "integration_version": _manifest_version(integration_dir / "manifest.json"),
        "home_assistant_version": _safe_version(home_assistant_version),
        "localtuya_version": localtuya_version,
        "configuration": config_state,
        "localtuya": localtuya,
        "humidifier": humidifier,
        "linked_entities": linked,
        "homekit_bridge": bridge,
        "native_ui": native_ui_status(hass),
        "recommendation": recommendation,
        # Historical LocalTuya handshake errors are NOT observable via HA
        # state alone. Never infer a root cause from 'unavailable'.
        "protocol_error": "not_available_from_entity_state",
    }
