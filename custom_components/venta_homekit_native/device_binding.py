"""Read-only source identity contract for the Venta logical device (P06).

The source remains owned by LocalTuya. Never add our config entry to its
DeviceEntry, move its entities, or copy its physical identifiers/connections.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

DOMAIN = "venta_homekit_native"


class BindingError(ValueError):
    """Privacy-safe rejection of a missing or changed source."""


def source_identity(source: Any, device: Any, config_entry: Any) -> str:
    """Derive a stable logical identifier, independent of entity names.

    A different config entry, device or source unique ID requires review.
    The input identifiers never leave this process in plain text.
    """
    if source is None or device is None or config_entry is None:
        raise BindingError("source_missing")
    if (
        getattr(source, "platform", None) != "localtuya"
        or not isinstance(getattr(source, "entity_id", None), str)
        or not source.entity_id.startswith("humidifier.")
        or getattr(config_entry, "domain", None) != "localtuya"
    ):
        raise BindingError("wrong_source")
    if any(getattr(item, "disabled_by", None) is not None
           for item in (source, device, config_entry)) or getattr(source, "hidden_by", None) is not None:
        raise BindingError("source_disabled")
    identity = (
        getattr(source, "config_entry_id", None),
        getattr(source, "device_id", None),
        getattr(source, "unique_id", None),
    )
    if not all(isinstance(value, str) and value for value in identity):
        raise BindingError("source_identity_missing")
    if (
        identity[0] != getattr(config_entry, "entry_id", None)
        or identity[0] != getattr(device, "config_entry_id", None)
        or identity[1] != getattr(device, "id", None)
    ):
        raise BindingError("source_ownership_changed")
    return hashlib.sha256(
        json.dumps(["venta-aw730-source-v1", *identity], separators=(",", ":")).encode()
    ).hexdigest()


def resolve_source(hass: Any, entity_id: str, *, expected: str | None = None) -> str:
    """Read the current registry before registration or delegated commands."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    source = er.async_get(hass).async_get(entity_id)
    if source is None or not getattr(source, "device_id", None):
        raise BindingError("source_missing")
    device = dr.async_get(hass).async_get(source.device_id)
    config_entry = hass.config_entries.async_get_entry(source.config_entry_id)
    identity = source_identity(source, device, config_entry)
    if expected is not None and expected != identity:
        raise BindingError("source_identity_changed")
    return identity


def logical_device_info(identity: str) -> dict[str, Any]:
    """Metadata for a separate Venta device; never claim physical ownership."""
    if not isinstance(identity, str) or len(identity) != 64 or any(
        char not in "0123456789abcdef" for char in identity
    ):
        raise BindingError("invalid_logical_identity")
    return {
        "identifiers": {(DOMAIN, "localtuya-" + identity)},
        "manufacturer": "Venta",
        "model": "AW730",
        "name": "Venta AW730 (LocalTuya)",
    }
