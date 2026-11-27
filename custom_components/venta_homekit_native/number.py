"""Optional, explicitly mapped Venta relative humidity correction."""
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.entity import EntityCategory
from .native_entity import VentaEntity, active_controller
from .native_control import ControlError

async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None and "rh_offset" in controller.extra_roles:
        async_add_entities([VentaOffset(controller, entry.entry_id)])

class VentaOffset(VentaEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = -10
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_rh_offset")

    @property
    def native_value(self):
        try:
            return self.controller.extra_value("rh_offset")
        except ControlError:
            return None

    @property
    def available(self):
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value):
        await self._command(self.controller.set_extra, "rh_offset", value)
