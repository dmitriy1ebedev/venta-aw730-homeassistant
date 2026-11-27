"""Optional, explicitly mapped Venta LED colour."""
from homeassistant.components.select import SelectEntity
from .native_entity import VentaEntity, active_controller
from .native_control import COLORS, ControlError

async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None and "led_color" in controller.extra_roles:
        async_add_entities([VentaColor(controller, entry.entry_id)])

class VentaColor(VentaEntity, SelectEntity):
    _attr_options = list(COLORS)

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_led_color")

    @property
    def current_option(self):
        try:
            return self.controller.extra_value("led_color")
        except ControlError:
            return None

    @property
    def available(self):
        return super().available and self.current_option is not None

    async def async_select_option(self, option):
        await self._command(self.controller.set_extra, "led_color", option)
