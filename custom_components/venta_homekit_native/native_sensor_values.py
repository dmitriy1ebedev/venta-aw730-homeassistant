"""Validated sensor projections. Never infer optional DP mappings."""
from __future__ import annotations

import hashlib
import json
from math import isfinite

from .native_control import ControlError

# HA-facing source units. Never relabel a value with a different unit.
SENSOR_SPECS = {
    "temperature": ("temperature", ("\N{DEGREE SIGN}C", "\N{DEGREE SIGN}F", "K"), None, None),
    "humidity": ("humidity", ("%",), 0, 100),
    "pm25": ("pm25", ("\N{MICRO SIGN}g/m\N{SUPERSCRIPT THREE}", "\N{GREEK SMALL LETTER MU}g/m\N{SUPERSCRIPT THREE}"), 0, None),
    "water_level": (None, ("%",), 0, 100),
    "filter_days": ("duration", ("d",), 0, 100000),
    "cleaning_days": ("duration", ("d",), 0, 100000),
    "service_days": ("duration", ("d",), 0, 100000),
}
OPTIONAL = frozenset(SENSOR_SPECS) - {"temperature", "humidity"}


def sample_value(role, state):
    """Return (numeric value, actual unit) or None; never invent zero."""
    if state is None:
        return None
    klass, units, low, high = SENSOR_SPECS[role]
    unit = state.attributes.get("unit_of_measurement")
    actual_class = state.attributes.get("device_class")
    if unit not in units or actual_class not in (None, klass):
        return None
    # PM2.5 must be positively classified, not just any mass-concentration sensor.
    if role == "pm25" and actual_class != klass:
        return None
    try:
        if isinstance(state.state, bool):
            return None
        value = float(state.state)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        return None
    if role == "temperature":
        absolute_zero = {"\N{DEGREE SIGN}C": -273.15, "\N{DEGREE SIGN}F": -459.67, "K": 0}
        if value < absolute_zero[unit]:
            return None
    if role == "temperature":
        if unit == "\N{DEGREE SIGN}F":
            value = (value - 32) * 5 / 9
        elif unit == "K":
            value -= 273.15
        unit = units[0]
        if not isfinite(value):
            return None
    # HA's canonical PM2.5 unit uses the micro sign; the Greek-mu spelling
    # is dimensionally identical and occurs in the bundled LocalTuya template.
    if role == "pm25":
        unit = units[0]
    return value, unit


def sensor_fingerprint(source, row, role, identity):
    """Identity and registry class check for an explicitly selected sensor."""
    unique = getattr(row, "unique_id", None)
    if (
        role not in OPTIONAL or source is None or row is None
        or not isinstance(getattr(row, "entity_id", None), str)
        or not row.entity_id.startswith("sensor.")
        or getattr(row, "platform", None) != "localtuya"
        or getattr(row, "device_id", None) != source.device_id
        or getattr(row, "config_entry_id", None) != source.config_entry_id
        or getattr(row, "disabled_by", None) is not None
        or getattr(row, "hidden_by", None) is not None
        or not isinstance(unique, str) or not unique
    ):
        raise ControlError("sensor_binding_invalid")
    klass = getattr(row, "device_class", None) or getattr(row, "original_device_class", None)
    expected = SENSOR_SPECS[role][0]
    if klass not in (None, expected) or (role == "pm25" and klass != expected):
        raise ControlError("sensor_class_invalid")
    return hashlib.sha256(json.dumps(
        ["venta-native-sensor-v1", identity, role, unique],
        separators=(",", ":"),
    ).encode()).hexdigest()


class NativeSensors:
    """Optional sensor identity pins, separate from the control adapter."""

    def __init__(self, controller, configured, expected=None):
        self.controller = controller
        self.roles = {}
        self.pins = {}
        if not isinstance(configured, dict) or (expected is not None and not isinstance(expected, dict)):
            raise ControlError("sensor_mapping_invalid")
        registry = controller._registry()
        source = registry.async_get(controller.roles["humidifier"])
        used = set(controller.roles.values())
        for role, entity_id in configured.items():
            if role not in OPTIONAL or not isinstance(entity_id, str) or entity_id in used:
                continue
            try:
                pin = sensor_fingerprint(source, registry.async_get(entity_id), role, controller.identity)
            except ControlError:
                continue
            if expected is not None and expected.get(role) != pin:
                continue
            used.add(entity_id)
            self.roles[role] = entity_id
            self.pins[role] = pin

    def state(self, role):
        if role in ("temperature", "humidity"):
            return self.controller.state(role)
        if role not in self.roles:
            raise ControlError("sensor_binding_invalid")
        registry = self.controller._registry()
        source = registry.async_get(self.controller.roles["humidifier"])
        row = registry.async_get(self.roles[role])
        if sensor_fingerprint(source, row, role, self.controller.identity) != self.pins[role]:
            raise ControlError("sensor_identity_changed")
        state = self.controller.hass.states.get(self.roles[role])
        if state is None or state.state in ("unknown", "unavailable"):
            raise ControlError("source_unavailable")
        return state

    def sample(self, role):
        try:
            return sample_value(role, self.state(role))
        except ControlError:
            return None
