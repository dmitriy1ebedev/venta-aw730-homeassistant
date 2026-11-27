"""Native read-only Venta sensors, grouped with the logical device."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.core import callback

from .device_binding import DOMAIN
from .native_entity import VentaEntity, active_controller
from .native_sensor_values import SENSOR_SPECS


async def async_setup_entry(hass, entry, async_add_entities):
    controller = active_controller(hass, entry)
    sensors = hass.data.get(DOMAIN, {}).get("native_sensors")
    if controller is not None and sensors is not None:
        roles = ("temperature", "humidity", *sorted(sensors.roles))
        async_add_entities([VentaSensor(controller, entry.entry_id, sensors, role) for role in roles])


class VentaSensor(VentaEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, controller, entry_id, sensors, role):
        super().__init__(controller, entry_id, "native_" + role)
        self.sensors = sensors
        self.role = role
        klass = SENSOR_SPECS[role][0]
        self._attr_device_class = SensorDeviceClass(klass) if klass else None
        if role not in ("temperature", "humidity", "pm25"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return super().available and self.sensors.sample(self.role) is not None

    @property
    def native_value(self):
        sample = self.sensors.sample(self.role)
        return sample[0] if sample is not None else None

    @property
    def native_unit_of_measurement(self):
        sample = self.sensors.sample(self.role)
        return sample[1] if sample is not None else SENSOR_SPECS[self.role][1][0]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.role in self.sensors.roles:
            @callback
            def changed(_event):
                self.async_write_ha_state()

            self.async_on_remove(async_track_state_change_event(
                self.hass, (self.sensors.roles[self.role],), changed))

            @callback
            def registry_changed(event):
                if event.data.get("entity_id") == self.sensors.roles[self.role]:
                    self.async_write_ha_state()

            self.async_on_remove(self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, registry_changed))
