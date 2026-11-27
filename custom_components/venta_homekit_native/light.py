"""Native brightness-capable LED control, no invented RGB capability."""
from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from .native_entity import VentaEntity, active_controller
from .native_control import LED_OPTIONS


async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None:
        async_add_entities([VentaLight(controller, entry.entry_id)])


class VentaLight(VentaEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_led")

    @property
    def available(self):
        led, brightness = self._source("led"), self._source("brightness")
        return (super().available and led is not None and led.state in ("on", "off")
                and brightness is not None and brightness.state in LED_OPTIONS)

    @property
    def is_on(self):
        source = self._source("led")
        return source is not None and source.state == "on"

    @property
    def brightness(self):
        source = self._source("brightness")
        return round(int(source.state) * 255 / 8) if source is not None and source.state in LED_OPTIONS else None

    async def async_turn_on(self, **kwargs):
        await self._command(self.controller.led, True, kwargs.get(ATTR_BRIGHTNESS))

    async def async_turn_off(self, **kwargs):
        await self._command(self.controller.led, False)
