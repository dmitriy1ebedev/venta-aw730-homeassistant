"""Read-only entity-registry discovery for a future Venta config flow.

No Home Assistant services, configuration writes, network calls or implicit
entity choices. Candidates must belong to the same LocalTuya device AND entry.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

ROLES: dict[str, str] = {
    "fan": "select",
    "led": "switch",
    "brightness": "select",
    "temperature": "sensor",
    "humidity": "sensor",
}
_SENSOR_CLASS = {"temperature": "temperature", "humidity": "humidity"}
_PLATFORM = "localtuya"


class DiscoveryError(ValueError):
    """Machine-readable, privacy-safe reason for rejecting discovery."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require_humidifier(entry: Any) -> None:
    if entry is None:
        raise DiscoveryError("humidifier_not_registered")
    entity_id = getattr(entry, "entity_id", None)
    if not isinstance(entity_id, str) or not entity_id.startswith("humidifier."):
        raise DiscoveryError("not_a_humidifier")
    if getattr(entry, "platform", None) != _PLATFORM:
        raise DiscoveryError("not_localtuya")
    if getattr(entry, "disabled_by", None) is not None:
        raise DiscoveryError("humidifier_disabled")
    if not getattr(entry, "device_id", None):
        raise DiscoveryError("device_id_missing")
    if not getattr(entry, "config_entry_id", None):
        raise DiscoveryError("config_entry_missing")


def _same_device_and_source(entry: Any, humidifier: Any) -> bool:
    """A shared config entry is insufficient: LocalTuya may have many devices."""
    return bool(
        entry is not None
        and getattr(entry, "device_id", None) == humidifier.device_id
        and getattr(entry, "config_entry_id", None) == humidifier.config_entry_id
        and getattr(entry, "platform", None) == _PLATFORM
        and getattr(entry, "disabled_by", None) is None
        and getattr(entry, "hidden_by", None) is None
        and isinstance(getattr(entry, "entity_id", None), str)
    )


def _sensor_class(entry: Any) -> str | None:
    value = getattr(entry, "device_class", None) or getattr(entry, "original_device_class", None)
    return str(value) if value is not None else None


def _eligible(entry: Any, role: str) -> bool:
    if not entry.entity_id.startswith(ROLES[role] + "."):
        return False
    if role in _SENSOR_CLASS:
        value = _sensor_class(entry)
        # Never suggest a sensor classified as PM2.5, energy, etc.
        return value is None or value == _SENSOR_CLASS[role]
    return True


def plan_from_entries(humidifier: Any, device_entries: Iterable[Any]) -> dict[str, Any]:
    """Provide UI choices without automatically selecting or persisting them.

    Suggested means a UI hint; all roles require explicit user confirmation.
    """
    _require_humidifier(humidifier)
    same_device: dict[str, Any] = {}
    for entry in device_entries:
        if _same_device_and_source(entry, humidifier) and entry.entity_id != humidifier.entity_id:
            if entry.entity_id in same_device:
                raise DiscoveryError("duplicate_registry_entry")
            same_device[entry.entity_id] = entry

    roles: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        candidates = [
            entry for _, entry in sorted(same_device.items())
            if _eligible(entry, role)
        ]
        options = [item.entity_id for item in candidates]
        unknown_class = [
            item.entity_id for item in candidates
            if role in _SENSOR_CLASS and _sensor_class(item) is None
        ]
        # Fan and brightness share select domain; do not infer the mapping.
        suggested = (
            options[0] if len(options) == 1
            and role not in ("fan", "brightness")
            and not unknown_class else None
        )
        status = (
            "missing" if not options
            else "review_class" if unknown_class
            else "manual_choice" if role in ("fan", "brightness") or len(options) > 1
            else "confirm"
        )
        roles[role] = {
            "options": options,
            "suggested": suggested,
            "status": status,
            "unclassified": unknown_class,
            "requires_confirmation": True,
        }

    return {
        "status": "review_required",
        "roles": roles,
        "can_submit": all(v["status"] != "missing" for v in roles.values()),
        "read_only": True,
    }


def validate_selection(
    humidifier: Any,
    device_entries: Iterable[Any],
    selections: Mapping[str, Any],
    *,
    confirmed_unclassified: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Return privacy-safe errors or an empty dict for explicit safe choices.

    Re-read the registry immediately before saving the config entry: mappings
    can change after the UI form first loads.
    """
    _require_humidifier(humidifier)
    entries: dict[str, Any] = {}
    duplicate_entries: set[str] = set()
    for item in device_entries:
        value = getattr(item, "entity_id", None)
        if isinstance(value, str):
            if value in entries:
                duplicate_entries.add(value)
            entries[value] = item
    errors: dict[str, str] = {}
    if set(selections) != set(ROLES):
        errors["_form"] = "all_five_roles_required"
    if not confirmed_unclassified.issubset(_SENSOR_CLASS.keys()):
        errors["_confirmation"] = "invalid_sensor_confirmation"
    used: set[str] = set()
    for role in ROLES:
        entity_id = selections.get(role)
        if not isinstance(entity_id, str) or not entity_id:
            errors[role] = "required"
            continue
        if entity_id in used or entity_id == humidifier.entity_id:
            errors[role] = "duplicate_entity"
            continue
        used.add(entity_id)
        entry = entries.get(entity_id)
        if entity_id in duplicate_entries:
            errors[role] = "duplicate_registry_entry"
        elif entry is None:
            errors[role] = "entity_not_registered"
        elif not _same_device_and_source(entry, humidifier):
            errors[role] = "different_or_disabled_device"
        elif not _eligible(entry, role):
            errors[role] = "incompatible_entity_domain_or_class"
        elif (
            role in _SENSOR_CLASS and _sensor_class(entry) is None
            and role not in confirmed_unclassified
        ):
            errors[role] = "sensor_class_confirmation_required"
    return errors


def discover_from_hass(hass: Any, humidifier_entity_id: str) -> dict[str, Any]:
    """Official HA 2026.11 entity-registry read-only adapter."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    humidifier = registry.async_get(humidifier_entity_id)
    _require_humidifier(humidifier)
    return plan_from_entries(
        humidifier, er.async_entries_for_device(registry, humidifier.device_id)
    )


def validate_from_hass(
    hass: Any,
    humidifier_entity_id: str,
    selections: Mapping[str, Any],
    *,
    confirmed_unclassified: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Read live registry again on submit rather than trusting cached UI."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    humidifier = registry.async_get(humidifier_entity_id)
    _require_humidifier(humidifier)
    return validate_selection(
        humidifier,
        er.async_entries_for_device(registry, humidifier.device_id),
        selections,
        confirmed_unclassified=confirmed_unclassified,
    )
