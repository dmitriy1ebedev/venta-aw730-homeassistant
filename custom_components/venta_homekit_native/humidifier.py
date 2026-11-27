"""Standard HA humidifier controls delegated to the existing LocalTuya entity."""
from homeassistant.components.humidifier import (
    HumidifierDeviceClass, HumidifierEntity, HumidifierEntityFeature,
)
from .native_entity import VentaEntity, active_controller
from .native_control import MODES


async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    if controller is not None:
        async_add_entities([VentaHumidifier(controller, entry.entry_id)])


class VentaHumidifier(VentaEntity, HumidifierEntity):
    _attr_device_class = HumidifierDeviceClass.HUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_min_humidity = 30
    _attr_max_humidity = 70
    _attr_target_humidity_step = 1
    _attr_available_modes = list(MODES)

    def __init__(self, controller, entry_id):
        super().__init__(controller, entry_id, "native_humidifier")

    @property
    def is_on(self):
        source = self._source("humidifier")
        return source is not None and source.state == "on"

    @property
    def target_humidity(self):
        source = self._source("humidifier")
        return source.attributes.get("humidity") if source is not None else None

    @property
    def current_humidity(self):
        source = self._source("humidity")
        try:
            value = float(source.state)
            return value if 0 <= value <= 100 else None
        except (ValueError, TypeError, AttributeError):
            return None

    @property
    def mode(self):
        source = self._source("humidifier")
        value = source.attributes.get("mode") if source is not None else None
        return value if value in MODES else None

    async def async_turn_on(self, **kwargs):
        await self._command(self.controller.power, True)

    async def async_turn_off(self, **kwargs):
        await self._command(self.controller.power, False)

    async def async_set_humidity(self, humidity):
        await self._command(self.controller.target_humidity, humidity)

    async def async_set_mode(self, mode):
        await self._command(self.controller.mode, mode)
