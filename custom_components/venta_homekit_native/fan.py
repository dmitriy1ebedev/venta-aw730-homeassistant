"""Five-step native fan control, sharing the existing washer power and mode."""
from homeassistant.components.fan import FanEntity, FanEntityFeature
from .native_entity import VentaEntity, active_controller
from .native_control import FAN_OPTIONS


async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None:
        async_add_entities([VentaFan(controller, entry.entry_id)])


class VentaFan(VentaEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    _attr_speed_count = 5

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_fan")

    @property
    def available(self):
        source = self._source("fan")
        return super().available and source is not None and source.state in FAN_OPTIONS

    @property
    def is_on(self):
        source = self._source("humidifier")
        return source is not None and source.state == "on"

    @property
    def percentage(self):
        source = self._source("fan")
        if not self.is_on:
            return 0
        return int(source.state) * 20 if source is not None and source.state in FAN_OPTIONS else None

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if percentage is None:
            await self._command(self.controller.power, True)
        else:
            await self._command(self.controller.fan_percentage, percentage)

    async def async_turn_off(self, **kwargs):
        await self._command(self.controller.power, False)

    async def async_set_percentage(self, percentage):
        await self._command(self.controller.fan_percentage, percentage)
