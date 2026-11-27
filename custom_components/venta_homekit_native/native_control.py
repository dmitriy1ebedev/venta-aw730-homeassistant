"""Validated, non-optimistic commands for the Venta HA user interface.

All I/O is delegated to existing HA services. Never create a Tuya connection
or modify registry ownership. The controller does not export any entities.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from typing import Any

from .device_binding import BindingError, resolve_source

DOMAINS = {"humidifier": "humidifier", "fan": "select", "led": "switch",
           "brightness": "select", "temperature": "sensor", "humidity": "sensor"}
MODES = ("Auto", "Manual", "Sleep")
FAN_OPTIONS = tuple(str(i) for i in range(1, 6))
LED_OPTIONS = tuple(str(i) for i in range(1, 9))


class ControlError(ValueError):
    """Stable, privacy-safe reason why a command could not be completed."""


def _integer(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ControlError("invalid_value")
    if not minimum <= value <= maximum or not math.isfinite(value) or int(value) != value:
        raise ControlError("invalid_value")
    return int(value)


def _role_fingerprint(source, row, role: str, identity: str) -> str:
    """Bind role to the confirmed source and original registry unique ID."""
    entity_id = getattr(row, "entity_id", None)
    unique = getattr(row, "unique_id", None)
    if (
        row is None or not isinstance(entity_id, str)
        or not entity_id.startswith(DOMAINS[role] + ".")
        or getattr(row, "platform", None) != "localtuya"
        or getattr(row, "device_id", None) != source.device_id
        or getattr(row, "config_entry_id", None) != source.config_entry_id
        or getattr(row, "disabled_by", None) is not None
        or getattr(row, "hidden_by", None) is not None
        or not isinstance(unique, str) or not unique
    ):
        raise ControlError("role_binding_invalid")
    return hashlib.sha256(
        json.dumps(["venta-native-role-v1", identity, role, unique],
                   separators=(",", ":")).encode()
    ).hexdigest()


class NativeControl:
    """Serializes commands, checks role identity immediately before each write."""

    def __init__(self, hass, source_identity: str, roles: dict[str, str],
                 *, expected_roles: dict[str, str] | None = None,
                 readback_timeout: float = 6.0):
        self.hass = hass
        self.identity = source_identity
        self.roles = dict(roles)
        if set(self.roles) != set(DOMAINS) or len(set(self.roles.values())) != len(DOMAINS):
            raise ControlError("invalid_role_mapping")
        if not 0 < readback_timeout <= 15:
            raise ControlError("invalid_readback_timeout")
        self.readback_timeout = readback_timeout
        self._lock = asyncio.Lock()
        fingerprints = self._fingerprints()
        if expected_roles is not None and fingerprints != expected_roles:
            raise ControlError("role_identity_changed")
        self.role_identities = fingerprints

    def _registry(self):
        from homeassistant.helpers import entity_registry as er

        try:
            resolve_source(self.hass, self.roles["humidifier"], expected=self.identity)
        except BindingError as exc:
            raise ControlError("source_identity_changed") from exc
        return er.async_get(self.hass)

    def _fingerprints(self) -> dict[str, str]:
        registry = self._registry()
        source = registry.async_get(self.roles["humidifier"])
        return {
            role: _role_fingerprint(source, registry.async_get(entity_id), role, self.identity)
            for role, entity_id in self.roles.items()
        }

    def _check_role(self, role: str) -> None:
        registry = self._registry()
        source = registry.async_get(self.roles["humidifier"])
        fingerprint = _role_fingerprint(
            source, registry.async_get(self.roles[role]), role, self.identity)
        if self.role_identities[role] != fingerprint:
            raise ControlError("role_identity_changed")

    def state(self, role: str):
        """Actual HA state only; no optimistic cache or synthetic values."""
        if role not in DOMAINS:
            raise ControlError("invalid_role")
        self._check_role(role)
        state = self.hass.states.get(self.roles[role])
        if state is None or state.state in ("unknown", "unavailable"):
            raise ControlError("source_unavailable")
        return state

    def _power_state(self) -> str:
        value = self.state("humidifier").state
        if value not in ("on", "off"):
            raise ControlError("source_unavailable")
        return value

    def _options(self, role: str, required: tuple[str, ...]) -> None:
        attr = "available_modes" if role == "humidifier" else "options"
        options = self.state(role).attributes.get(attr)
        if (not isinstance(options, (list, tuple))
                or not all(isinstance(item, str) for item in options)
                or not set(required).issubset(options)):
            raise ControlError("source_options_changed")

    async def _wait(self, role, predicate) -> None:
        from homeassistant.core import callback
        from homeassistant.helpers.event import async_track_state_change_event

        event = asyncio.Event()
        entity_id = self.roles[role]

        @callback
        def changed(_event):
            event.set()

        unsubscribe = async_track_state_change_event(self.hass, (entity_id,), changed)
        try:
            async with asyncio.timeout(self.readback_timeout):
                while True:
                    event.clear()
                    self._power_state()
                    if predicate(self.state(role)):
                        return
                    await event.wait()
        except TimeoutError as exc:
            raise ControlError("readback_timeout") from exc
        finally:
            unsubscribe()

    def _ensure_services(self, *services: tuple[str, str]) -> None:
        if any(not self.hass.services.has_service(*service) for service in services):
            raise ControlError("service_unavailable")

    async def _send(self, role, domain, service, parameters, predicate, context) -> None:
        self._power_state()
        state = self.state(role)
        if predicate(state):
            return
        self._ensure_services((domain, service))
        # Only known service and confirmed role IDs are passed to HA. No
        # arbitrary caller-supplied service names or target entity IDs.
        await self.hass.services.async_call(
            domain, service, {"entity_id": self.roles[role], **parameters},
            blocking=True, context=context,
        )
        await self._wait(role, predicate)

    async def _power(self, enabled: bool, context) -> None:
        expected = "on" if enabled else "off"
        await self._send("humidifier", "humidifier", "turn_on" if enabled else "turn_off",
                         {}, lambda state: state.state == expected, context)

    async def power(self, enabled: bool, *, context=None) -> None:
        if not isinstance(enabled, bool):
            raise ControlError("invalid_value")
        async with self._lock:
            await self._power(enabled, context)

    async def target_humidity(self, humidity: int, *, context=None) -> None:
        humidity = _integer(humidity, 30, 70)
        async with self._lock:
            await self._send(
                "humidifier", "humidifier", "set_humidity", {"humidity": humidity},
                lambda state: state.attributes.get("humidity") == humidity, context,
            )

    async def _mode(self, mode: str, context) -> None:
        self._options("humidifier", MODES)
        if self._power_state() != "on":
            raise ControlError("power_on_required")
        await self._send("humidifier", "humidifier", "set_mode", {"mode": mode},
                         lambda state: state.attributes.get("mode") == mode, context)

    async def mode(self, mode: str, *, context=None) -> None:
        if mode not in MODES:
            raise ControlError("invalid_value")
        async with self._lock:
            await self._mode(mode, context)

    async def fan_percentage(self, percentage: int, *, context=None) -> None:
        percentage = _integer(percentage, 0, 100)
        async with self._lock:
            if percentage == 0:
                await self._power(False, context)
                return
            # Verify all roles and mode choices before a multi-step command.
            self._options("fan", FAN_OPTIONS)
            self._options("humidifier", MODES)
            level = str(max(1, min(5, (percentage + 10) // 20)))
            self._ensure_services(("humidifier", "set_mode"), ("select", "select_option"))
            if self._power_state() == "off":
                self._ensure_services(("humidifier", "turn_on"))
                await self._power(True, context)
            self._options("fan", FAN_OPTIONS)
            await self._mode("Manual", context)
            self._options("fan", FAN_OPTIONS)
            await self._send("fan", "select", "select_option", {"option": level},
                             lambda state: state.state == level, context)

    async def led(self, enabled: bool, brightness: int | None = None, *, context=None) -> None:
        if not isinstance(enabled, bool):
            raise ControlError("invalid_value")
        if brightness is not None:
            brightness = _integer(brightness, 0, 255)
            if brightness == 0:
                enabled = False
            if not enabled and brightness > 0:
                raise ControlError("invalid_value")
        async with self._lock:
            self._power_state()
            if self.state("led").state not in ("on", "off"):
                raise ControlError("source_unavailable")
            if enabled and brightness is not None:
                self._options("brightness", LED_OPTIONS)
                self._ensure_services(("select", "select_option"))
            desired = "on" if enabled else "off"
            await self._send("led", "switch", "turn_on" if enabled else "turn_off",
                             {}, lambda state: state.state == desired, context)
            if enabled and brightness is not None:
                level = str(max(1, min(8, (brightness * 8 + 127) // 255)))
                self._options("brightness", LED_OPTIONS)
                await self._send(
                    "brightness", "select", "select_option", {"option": level},
                    lambda state: state.state == level, context,
                )
