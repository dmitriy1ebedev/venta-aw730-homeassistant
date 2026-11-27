"""Optional, explicitly mapped Venta hybrid mode."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from .native_entity import VentaEntity, active_controller
from .native_control import ControlError

async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None and "hybrid" in controller.extra_roles:
        async_add_entities([VentaHybrid(controller, entry.entry_id)])

class VentaHybrid(VentaEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_hybrid")

    @property
    def is_on(self):
        try:
            return self.controller.extra_value("hybrid")
        except ControlError:
            return None

    @property
    def available(self):
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs):
        await self._command(self.controller.set_extra, "hybrid", True)

    async def async_turn_off(self, **kwargs):
        await self._command(self.controller.set_extra, "hybrid", False)
