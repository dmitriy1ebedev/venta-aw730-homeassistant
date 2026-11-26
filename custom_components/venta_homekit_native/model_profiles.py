"""Immutable public Venta model contracts, with no discovery or device I/O.

A mapping is evidence of the bundled template, not certification of every DP
or firmware. Keep legacy AW730 bindings unchanged. Never select another model
by similarity or fall back to AW730 for an unknown product.
"""
from __future__ import annotations

from typing import NamedTuple


class EntityMapping(NamedTuple):
    role: str
    platform: str
    dp: str
    name: str
    access: str
    options: tuple[tuple[str, str], ...] = ()
    unit: str | None = None
    bounds: tuple[float, float, float] | None = None


class ModelProfile(NamedTuple):
    model: str
    protocol: str
    template: str
    template_sha256: str
    firmware: str | None
    target_dp: str
    current_dp: str
    mode_dp: str
    humidity_range: tuple[int, int]
    modes: tuple[tuple[str, str], ...]
    entities: tuple[EntityMapping, ...]

    def entity(self, role: str) -> EntityMapping | None:
        return next((entity for entity in self.entities if entity.role == role), None)

    @property
    def fan_levels(self) -> int:
        return len(self.entity("fan").options)

    @property
    def fan_step_percent(self) -> int:
        return 100 // self.fan_levels

    @property
    def brightness_levels(self) -> int:
        return len(self.entity("brightness").options)


AW730 = ModelProfile(
    model="AW730",
    protocol="3.4",
    template="venta_aw730.yaml",
    template_sha256="f905e1ff0ff451b65a80fc3f7059cd8f7b76b1ad05f4e0e822b0f9977e4fb3ff",
    firmware=None,  # Physical firmware version was not independently recorded.
    target_dp="13",
    current_dp="14",
    mode_dp="24",
    humidity_range=(30, 70),
    modes=(("normal", "Manual"), ("automatic", "Auto"), ("sleep", "Sleep")),
    entities=(
        EntityMapping("power", "humidifier", "1", "", "control"),
        EntityMapping("temperature", "sensor", "10", "Temperature", "read", unit="°C"),
        EntityMapping("humidity", "sensor", "14", "Humidity", "read", unit="%"),
        EntityMapping("filter_reset", "button", "28", "Filter Reset", "unverified"),
        EntityMapping("cleaning_reset", "button", "104", "Cleaning Reset", "unverified"),
        EntityMapping("service_reset", "button", "108", "Service Reset", "unverified"),
        EntityMapping("color", "select", "113", "LED Color", "manual_config", options=(
            ("color1", "purple"), ("color2", "blue"), ("color3", "green"),
            ("color4", "light green"), ("color5", "lemon"), ("color6", "yellow"),
            ("color7", "orange"), ("aqi_visualization", "AQI"),
        )),
        EntityMapping("pm25", "sensor", "32", "PM2.5", "read", unit="μg/m³"),
        EntityMapping("filter", "sensor", "101", "Filter", "read", unit="d"),
        EntityMapping("water", "sensor", "102", "Water Level", "read", unit="%"),
        EntityMapping("fan", "select", "105", "Fan Speed", "control",
                      options=tuple((f"speed{i}", str(i)) for i in range(1, 6))),
        EntityMapping("brightness", "select", "106", "LEd Brightness", "control",
                      options=tuple((f"bright{i}", str(i)) for i in range(1, 9))),
        EntityMapping("cleaning", "sensor", "109", "Cleaning", "read", unit="d"),
        EntityMapping("service", "sensor", "111", "Service", "read", unit="d"),
        EntityMapping("hybrid", "switch", "112", "Hybrid Mode", "manual_config"),
        EntityMapping("led", "switch", "114", "LED on", "control"),
        EntityMapping("offset", "number", "116", "RH Offset", "manual_config",
                      unit="%", bounds=(-10.0, 10.0, 1.0)),
        EntityMapping("target", "number", "13", "Humidity Set", "manual_config",
                      unit="%", bounds=(30.0, 70.0, 1.0)),
    ),
)

PROFILES = (AW730,)


def get_profile(model: str, protocol: str) -> ModelProfile | None:
    """Exact match only; a match does not certify an untested firmware."""
    return next((p for p in PROFILES if (p.model, p.protocol) == (model, protocol)), None)


def template_errors(profile: ModelProfile, rows: object) -> tuple[str, ...]:
    """Check parsed bundled template, offline. Never accept live device data."""
    if not isinstance(rows, list) or len(rows) != len(profile.entities):
        return ("unexpected entity count",)
    errors = []
    for mapping, row in zip(profile.entities, rows):
        if not isinstance(row, dict) or tuple(row) != (mapping.platform,):
            errors.append(f"{mapping.role}: platform")
            continue
        entry = row[mapping.platform]
        if not isinstance(entry, dict):
            errors.append(f"{mapping.role}: invalid entry")
            continue
        expected = {"platform": mapping.platform, "id": mapping.dp, "friendly_name": mapping.name}
        if mapping.unit is not None:
            expected["unit_of_measurement"] = mapping.unit
        if mapping.bounds is not None:
            expected.update(zip(("min_value", "max_value", "step_size"), mapping.bounds))
        if mapping.platform in ("select", "switch", "number"):
            # Exact boolean values: false must not silently accept integer 0.
            for key in ("restore_on_reconnect", "is_passive_entity"):
                if entry.get(key) is not False:
                    errors.append(f"{mapping.role}: {key}")
        if mapping.options:
            # LocalTuya's YAML historically uses numeric labels for fan/brightness.
            # Compare the HA-facing string representation and preserve option order.
            options = entry.get("select_options")
            if not isinstance(options, dict) or tuple((k, str(v)) for k, v in options.items()) != mapping.options:
                errors.append(f"{mapping.role}: options")
        if mapping.platform == "humidifier":
            expected.update({
                "humidifier_set_humidity_dp": profile.target_dp,
                "humidifier_current_humidity_dp": profile.current_dp,
                "humidifier_mode_dp": profile.mode_dp,
                "min_humidity": profile.humidity_range[0],
                "max_humidity": profile.humidity_range[1],
            })
            modes = entry.get("humidifier_available_modes")
            if not isinstance(modes, dict) or tuple(modes.items()) != profile.modes:
                errors.append("power: modes")
        for key, value in expected.items():
            if entry.get(key) != value:
                errors.append(f"{mapping.role}: {key}")
        if mapping.access == "unverified" and entry.get("entity_category") != "diagnostic":
            errors.append(f"{mapping.role}: diagnostic category")
    return tuple(errors)
