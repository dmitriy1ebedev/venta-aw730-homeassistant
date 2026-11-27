"""Base for guarded native Venta control entities."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .device_binding import DOMAIN, logical_device_info
from .export_guard import export_blockers
from .native_control import ControlError


class VentaEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller, entry_id: str, suffix: str):
        super().__init__()
        self.controller = controller
        self.entry_id = entry_id
        self._attr_unique_id = controller.identity + "-" + suffix
        self._attr_translation_key = suffix
        self._attr_device_info = dr.DeviceInfo(**logical_device_info(controller.identity))

    def _exports_safe(self) -> bool:
        try:
            hass = self.controller.hass
            active = hass.data.get(DOMAIN, {})
            entry = hass.config_entries.async_get_entry(self.entry_id)
            return bool(
                entry is not None and entry.options.get("native_device_ui") is True
                and active.get("config_entry_id") == self.entry_id
                and active.get("native_ui_enabled") is True
                and active.get("native_control") is self.controller
                and not export_blockers(hass, self.entry_id)
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    @property
    def available(self) -> bool:
        if not self._exports_safe():
            return False
        try:
            return self.controller.state("humidifier").state in ("on", "off")
        except ControlError:
            return False

    def _source(self, role: str):
        try:
            return self.controller.state(role)
        except ControlError:
            return None

    async def _command(self, method, *args):
        if not self._exports_safe():
            raise HomeAssistantError("Venta: review HomeKit/Yaha export filters")
        try:
            await method(*args, context=self._context)
        except ControlError as exc:
            raise HomeAssistantError("Venta: " + str(exc)) from exc

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        @callback
        def changed(_event):
            self.async_write_ha_state()

        self.async_on_remove(async_track_state_change_event(
            self.hass, tuple(self.controller.roles.values()), changed,
        ))

        @callback
        def registry_changed(event):
            if event.data.get("entity_id") in self.controller.roles.values():
                self.async_write_ha_state()

        self.async_on_remove(self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, registry_changed))
        self.async_on_remove(self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, changed))


def active_controller(hass, entry):
    """Platforms are not exposed without the reviewed config-entry gate."""
    active = hass.data.get(DOMAIN, {})
    if active.get("config_entry_id") != entry.entry_id or not active.get("native_ui_enabled"):
        return None
    return active.get("native_control")
