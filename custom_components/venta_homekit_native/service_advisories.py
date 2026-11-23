"""Read-only service advisories from validated DP samples."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Advisory:
    kind: str
    severity: str

def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    n = float(value)
    return n if isfinite(n) and low <= n <= high else None

def sample_service_states(states, entity_ids):
    """Read configured HA entity states; return only numeric, privacy-safe DP values.

    Unknown, unavailable, missing and malformed states become None. No entity
    IDs, attributes, network addresses or other device metadata are returned.
    """
    sample = {}
    for role in ("water_level", "filter_days", "cleaning_days", "service_days"):
        entity_id = entity_ids.get(role)
        item = states.get(entity_id) if isinstance(entity_id, str) and entity_id else None
        raw = getattr(item, "state", None)
        if not isinstance(raw, str):
            sample[role] = None
            continue
        try:
            value = float(raw)
        except (ValueError, OverflowError):
            sample[role] = None
            continue
        maximum = 100 if role == "water_level" else 100000
        sample[role] = _number(value, 0, maximum)
    return sample


def classify_service_state(current, previous, *, available, previous_available=True):
    """Require consecutive samples; never issue device writes or resets."""
    if not available:
        return (Advisory("device_unavailable", "info"),)
    if not previous_available or previous is None:
        return ()
    result = []
    water = _number(current.get("water_level"), 0, 100)
    old = _number(previous.get("water_level"), 0, 100)
    if water is not None and old is not None and water <= 10 and old <= 10:
        result.append(Advisory("check_water_level", "warning"))
    for key in ("filter_days", "cleaning_days", "service_days"):
        now = _number(current.get(key), 0, 100000)
        before = _number(previous.get(key), 0, 100000)
        if now is not None and before is not None and now == 0 and before == 0:
            result.append(Advisory("inspect_" + key, "info"))
    return tuple(result)


class ServiceAdvisoryMonitor:
    """Consecutive-state advisory monitor with deduplicated HA notifications.

    Only explicitly configured entities are observed. HA persistent notifications
    are scoped to this integration, never written to the device.
    """
    _TITLES = {
        "check_water_level": "Venta: check water level",
        "inspect_filter_days": "Venta: inspect filter",
        "inspect_cleaning_days": "Venta: inspect cleaning interval",
        "inspect_service_days": "Venta: inspect service interval",
        "device_unavailable": "Venta: device unavailable",
    }

    def __init__(self, hass, humidifier_entity, sensor_entities):
        self.hass = hass
        self.humidifier_entity = humidifier_entity
        self.sensor_entities = dict(sensor_entities)
        self.previous = None
        self.previous_available = False
        self.active = set()

    def update(self):
        humidifier = self.hass.states.get(self.humidifier_entity)
        available = (
            humidifier is not None
            and getattr(humidifier, "state", None) not in ("unknown", "unavailable")
        )
        sample = sample_service_states(self.hass.states, self.sensor_entities)
        advisories = classify_service_state(
            sample, self.previous, available=available,
            previous_available=self.previous_available,
        )
        self.previous = sample if available else None
        self.previous_available = available
        wanted = {item.kind for item in advisories}
        # An unavailable device is reported as informational only, not an
        # alarm for individual counters whose values cannot be trusted.
        for kind in sorted(wanted - self.active):
            self.hass.async_create_task(self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": self._TITLES[kind],
                 "message": "Review the corresponding Venta status in Home Assistant.",
                 "notification_id": "venta_service_" + kind},
            ))
        for kind in sorted(self.active - wanted):
            self.hass.async_create_task(self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": "venta_service_" + kind},
            ))
        self.active = wanted

    def dismiss_all(self):
        for kind in sorted(self.active):
            self.hass.async_create_task(self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": "venta_service_" + kind},
            ))
        self.active.clear()
