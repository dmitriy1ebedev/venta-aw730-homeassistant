"""Conservative export admission for Venta UI projections.

Do not rewrite HomeKit or Yaha configuration. A broad, unavailable or
unrecognized export filter blocks new UI entities; the original bridge remains.
"""
from __future__ import annotations

from collections.abc import Mapping

DOMAIN = "venta_homekit_native"
# All currently supported Venta entity platforms; unknown future domains
# must be added here before enabling their platform.
PROJECTION_DOMAINS = frozenset({"humidifier", "fan", "light", "sensor", "select", "switch", "number"})


def _explicit_filter(filter_config, registry) -> bool:
    if not isinstance(filter_config, Mapping):
        return False
    if any(not isinstance(values, (list, tuple)) or not all(isinstance(value, str) and value for value in values)
           for values in filter_config.values()):
        return False
    # Broad inclusion of an unrelated domain (e.g. climate) cannot match
    # a Venta projection. Broad globs or overlapping domains remain unsafe.
    if set(filter_config.get("include_domains", ())) & PROJECTION_DOMAINS or filter_config.get("include_entity_globs"):
        return False
    if set(filter_config) - {
        "include_entities", "include_domains", "include_entity_globs",
        "exclude_entities", "exclude_domains", "exclude_entity_globs",
    }:
        return False
    ids = filter_config.get("include_entities", ())
    # An empty include list with no included domains is a broad default.
    if not ids and not filter_config.get("include_domains"):
        return False
    return all(
        isinstance(entity_id, str)
        and (row := registry.async_get(entity_id)) is not None
        and getattr(row, "platform", None) != DOMAIN
        for entity_id in ids
    )


def export_blockers(hass, entry_id: str) -> tuple[str, ...]:
    """Accept only existing non-Venta explicit exports or reviewed label mode."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    blockers = []
    venta_entries = {entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)}
    venta_entries.add(entry_id)
    for entry in hass.config_entries.async_entries("homekit"):
        options = entry.options
        if not isinstance(options, Mapping):
            blockers.append("homekit_filter_not_explicit")
            continue
        if not _explicit_filter(options.get("filter"), registry):
            blockers.append("homekit_filter_not_explicit")
        device_ids = options.get("devices", [])
        if not isinstance(device_ids, (list, tuple)) or any(
            not isinstance(device_id, str)
            or (device := device_registry.async_get(device_id)) is None
            or getattr(device, "config_entry_id", None) in venta_entries
            for device_id in device_ids
        ):
            blockers.append("homekit_device_export_conflict")
    for entry in hass.config_entries.async_entries("yandex_smart_home"):
        options = entry.options
        if not isinstance(options, Mapping):
            blockers.append("yaha_filter_unverified")
            continue
        source = options.get("filter_source")
        if source == "config_entry":
            if not _explicit_filter(options.get("filter"), registry):
                blockers.append("yaha_filter_not_explicit")
        elif source == "label":
            label = options.get("label")
            if not isinstance(label, str) or not label or any(
                getattr(row, "platform", None) == DOMAIN
                and label in getattr(row, "labels", ())
                for row in registry.entities.values()
            ):
                blockers.append("yaha_label_conflict")
        else:
            blockers.append("yaha_filter_unverified")
    return tuple(sorted(set(blockers)))
