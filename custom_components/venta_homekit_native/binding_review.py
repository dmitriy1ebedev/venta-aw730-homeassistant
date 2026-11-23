"""Read-only, exact-identity binding review for Venta UI options and repairs.

This module cannot modify HomeKit, LocalTuya, HA config entries, or devices.
All saved changes require explicit confirmation in a separate flow.
"""
from __future__ import annotations

from typing import Any

from .entity_discovery import (
    DiscoveryError,
    ROLES,
    discover_from_hass,
    validate_from_hass,
)

BRIDGE = "bridge_entry_id"
SOURCE = "humidifier_entity"
ROLE_FIELDS = tuple(f"{role}_entity" for role in ROLES)
IDENTITY_FIELDS = (SOURCE, BRIDGE, "bridge_title", *ROLE_FIELDS)


def bridge_choices(hass: Any) -> dict[str, str]:
    """List existing HA bridge-mode entries by entry_id, never by title."""
    return {
        e.entry_id: e.title
        for e in hass.config_entries.async_entries("homekit")
        if getattr(e, "entry_id", None)
        and isinstance(getattr(e, "title", None), str)
        and isinstance(getattr(e, "options", None), dict)
        and e.options.get("mode", "bridge") == "bridge"
    }


def validate_bridge(hass: Any, bridge_id: str, humidifier_id: str) -> str | None:
    """Reject a missing, excluded, or non-bridge HomeKit entry."""
    for entry in hass.config_entries.async_entries("homekit"):
        if entry.entry_id != bridge_id:
            continue
        options = getattr(entry, "options", None)
        if not isinstance(options, dict) or options.get("mode", "bridge") != "bridge":
            return "bridge_unavailable"
        filters = options.get("filter") or {}
        if not isinstance(filters, dict):
            return "bridge_unavailable"
        includes = filters.get("include_entities") or []
        excludes = filters.get("exclude_entities") or []
        if not isinstance(includes, (tuple, list)) or not isinstance(
            excludes, (tuple, list)
        ):
            return "bridge_unavailable"
        if (includes and humidifier_id not in includes) or humidifier_id in excludes:
            return "bridge_excludes_humidifier"
        return None
    return "bridge_unavailable"


def review_plan(hass: Any, saved: dict[str, Any]) -> dict[str, Any]:
    """Enumerate role candidates for the **saved** humidifier only."""
    source = saved.get(SOURCE)
    if not isinstance(source, str) or not source.startswith("humidifier."):
        raise DiscoveryError("humidifier_not_registered")
    return discover_from_hass(hass, source)


def review_proposal(
    hass: Any,
    current: dict[str, Any],
    bridge_id: Any,
    selections: dict[str, Any],
    *,
    confirmed_unclassified: frozenset[str] = frozenset(),
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Re-read both registries before accepting a proposal; never guess a role.

    Return field-safe reasons only. The proposed mapping is just structured
    data and is never applied to a live accessory by this function.
    """
    errors: dict[str, str] = {}
    source = current.get(SOURCE)
    if not isinstance(source, str):
        return {"base": "invalid_entity"}, None
    if not isinstance(bridge_id, str):
        errors[BRIDGE] = "bridge_unavailable"
    else:
        problem = validate_bridge(hass, bridge_id, source)
        if problem:
            errors[BRIDGE] = problem

    try:
        problems = validate_from_hass(
            hass, source, selections,
            confirmed_unclassified=confirmed_unclassified,
        )
    except (DiscoveryError, TypeError, ValueError):
        return {**errors, "base": "localtuya_humidifier_missing"}, None
    for role in ROLES:
        if role in problems:
            errors[f"{role}_entity"] = "invalid_entity"
    if "_form" in problems or "_confirmation" in problems:
        errors["base"] = "invalid_entity"
    if errors:
        return errors, None

    bridge = next(
        entry for entry in hass.config_entries.async_entries("homekit")
        if entry.entry_id == bridge_id
    )
    proposal = {
        SOURCE: source,
        BRIDGE: bridge_id,
        "bridge_title": bridge.title,
        "confirmed_unclassified": sorted(confirmed_unclassified),
        **{f"{role}_entity": selections[role] for role in ROLES},
    }
    return {}, proposal


def mapping_changed(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Detect substantive changes without treating bridge title as identity."""
    keys = (SOURCE, BRIDGE, *ROLE_FIELDS)
    return any(candidate.get(key) != current.get(key) for key in keys) or (
        sorted(candidate.get("confirmed_unclassified", []))
        != sorted(current.get("confirmed_unclassified", []))
    )
