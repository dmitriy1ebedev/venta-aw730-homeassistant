"""Extend *only* the existing Venta HomeKit bridge accessory.

Do not start a new HAP server, change pairing, or modify any other entity.
Uses Home Assistant's own HomeKit HomeAccessory and bridge lifecycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from homeassistant.const import __version__ as HA_VERSION
from .diagnostics import collect_diagnostics

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from pyhap.util import callback as pyhap_callback
from pyhap.characteristic import Characteristic
from pyhap.service import Service

from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Event, HassJobType, HomeAssistant, State, SupportsResponse, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.components.homekit.accessories import TYPES
from homeassistant.components.homekit.const import SIGNAL_RELOAD_ENTITIES, STATUS_RUNNING
from homeassistant.components.homekit.type_humidifiers import (
    HumidifierDehumidifier as NativeHumidifierDehumidifier,
)
from .install_localtuya_template import sync_managed_template

DOMAIN = "venta_homekit_native"
ENTITY = BRIDGE_ENTRY = FAN = LED = BRIGHTNESS = TEMPERATURE = HUMIDITY = None
EXTRA_ENTITIES = ()
_LOGGER = logging.getLogger(__name__)

# Validate YAML configuration before async_setup. Preserve the existing
# seven public keys and permit future optional configuration values.
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN): vol.Schema(
            {
                vol.Required("humidifier_entity"): cv.entity_id,
                vol.Required("bridge_title"): cv.string,
                vol.Required("fan_entity"): cv.entity_id,
                vol.Required("led_entity"): cv.entity_id,
                vol.Required("brightness_entity"): cv.entity_id,
                vol.Required("temperature_entity"): cv.entity_id,
                vol.Required("humidity_entity"): cv.entity_id,
            },
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class VentaEnhancedHumidifier(NativeHumidifierDehumidifier):
    """Keep one HomeKit humidifier and attach native secondary controls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.entity_id != ENTITY:
            return

        main = self.get_service("HumidifierDehumidifier")
        self.set_primary_service(main)

        # The stock humidity characteristic already includes on/off,
        # current relative humidity, and 0..100% target. We retain its
        # original setter and clamp the physical device to 30..70%.
        # Apple Home has a built-in interface for these characteristics.
        self.linked_humidity_sensor = HUMIDITY

        # Dyson's publicly tested HomeKit humidifier uses 0 (Auto) and
        # 1 (Humidify), explicitly excluding 2 (Dehumidify).
        # Map Auto to Venta's automatic humidification program and
        # Humidify to its manual program without advertising dehumidification.
        target = self.char_target_humidifier_dehumidifier
        target.override_properties(
            properties={"minValue": 0, "maxValue": 1},
            valid_values={"Auto": 0, "Humidifier": 1},
        )
        current = self.hass.states.get(ENTITY)
        target.set_value(
            0 if current and current.attributes.get("mode") == "Auto" else 1
        )

        fan = self.add_preload_service(
            "Fanv2",
            ["RotationSpeed", "TargetFanState", "CurrentFanState", "Name"],
            unique_id="venta-fan-v1",
        )
        fan.configure_char("Name", value="Вентилятор")
        self._venta_fan_active = fan.configure_char("Active", value=0)
        self._venta_fan_speed = fan.configure_char("RotationSpeed", value=20)
        self._venta_fan_target = fan.configure_char("TargetFanState", value=1)
        self._venta_fan_current = fan.configure_char("CurrentFanState", value=0)
        fan.setter_callback = self._venta_set_fan
        main.add_linked_service(fan)

        # iOS Home hides automatic target=0 for a humidifier-only service
        # despite valid HAP metadata. Expose a clearly named, linked Auto
        # control rather than falsely advertising dehumidification.
        auto = self.add_preload_service(
            "Switch", ["Name"], unique_id="venta-auto-mode-v1",
        )
        auto.configure_char("Name", value="Авто")
        self._venta_auto_on = auto.configure_char("On", value=False)
        auto.setter_callback = self._venta_set_auto
        main.add_linked_service(auto)

        led = self.add_preload_service(
            "Lightbulb", ["Brightness", "Name"], unique_id="venta-led-v1",
        )
        led.configure_char("Name", value="Подсветка")
        self._venta_led_on = led.configure_char("On", value=False)
        self._venta_led_brightness = led.configure_char("Brightness", value=63)
        led.setter_callback = self._venta_set_led
        main.add_linked_service(led)

        temp = self.add_preload_service(
            "TemperatureSensor", ["Name"], unique_id="venta-temperature-v1",
        )
        temp.configure_char("Name", value="Температура")
        self._venta_temperature = temp.configure_char("CurrentTemperature", value=24.0)
        main.add_linked_service(temp)

        self._venta_update_extras()
        _LOGGER.info(
            "Native HomeKit Venta enhanced with 4 linked services: fan, auto, LED, temperature"
        )

    @callback
    @pyhap_callback
    def run(self):
        super().run()
        if self.entity_id != ENTITY:
            return
        self._subscriptions.append(
            async_track_state_change_event(
                self.hass,
                EXTRA_ENTITIES,
                self._venta_extra_event,
                job_type=HassJobType.Callback,
            )
        )
        self._venta_update_extras()
        if _LOGGER.isEnabledFor(logging.DEBUG):
            hap = self.char_target_humidifier_dehumidifier.to_HAP()
            _LOGGER.debug(
                "Venta target mode: %s",
                {k: hap.get(k) for k in ("minValue", "maxValue", "valid-values", "value")},
            )

    @callback
    def _venta_extra_event(self, event: Event):
        self._venta_update_extras()

    @callback
    def async_update_state(self, new_state: State):
        super().async_update_state(new_state)
        if self.entity_id == ENTITY and hasattr(self, "_venta_fan_active"):
            self.char_target_humidifier_dehumidifier.set_value(
                0 if new_state.attributes.get("mode") == "Auto" else 1
            )
            self._venta_update_extras()

    @callback
    def _set_chars(self, values: dict):
        if self.entity_id == ENTITY and "TargetHumidifierDehumidifierState" in values:
            choice = int(values["TargetHumidifierDehumidifierState"])
            if choice not in (0, 1):
                _LOGGER.warning("Venta: invalid humidifier target choice %s", choice)
                return
            self.hass.async_create_task(self._venta_apply_target(choice))
            self.char_target_humidifier_dehumidifier.set_value(choice)
            values = {k: v for k, v in values.items()
                      if k != "TargetHumidifierDehumidifierState"}
        if values:
            super()._set_chars(values)

    async def _venta_apply_target(self, choice: int):
        state = self.hass.states.get(ENTITY)
        if state is None or state.state in ("unknown", "unavailable"):
            _LOGGER.warning("Venta target ignored: underlying device unavailable")
            return
        # LocalTuya Venta ignores mode commands while switched off.
        if state.state == STATE_OFF:
            await self.hass.services.async_call(
                "humidifier", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True,
            )
        await self.hass.services.async_call(
            "humidifier", "set_mode",
            {ATTR_ENTITY_ID: ENTITY, "mode": "Auto" if choice == 0 else "Manual"},
            blocking=True,
        )

    @callback
    def _venta_set_auto(self, values: dict):
        if "On" not in values:
            return
        self.hass.async_create_task(
            self._venta_apply_auto_toggle(bool(values["On"]))
        )

    async def _venta_apply_auto_toggle(self, enable: bool):
        """Auto switch belongs to existing Venta accessory, never a new device."""
        if enable:
            await self._venta_apply_target(0)
            return
        # Turning *off* the Auto control means manual fan control, not power off.
        # Do not start an otherwise switched-off humidifier.
        state = self.hass.states.get(ENTITY)
        if (
            state is not None and state.state == STATE_ON
            and state.attributes.get("mode") == "Auto"
        ):
            await self.hass.services.async_call(
                "humidifier", "set_mode",
                {ATTR_ENTITY_ID: ENTITY, "mode": "Manual"},
                blocking=True,
            )

    @callback
    def _venta_set_fan(self, values: dict):
        """Apple Home fan Auto/Manual and speed operate one physical Venta."""
        self.hass.async_create_task(self._venta_apply_fan(values.copy()))

    async def _venta_apply_fan(self, values: dict):
        # Execute in order: the real device can ignore mode/speed while off.
        speed = float(values["RotationSpeed"]) if "RotationSpeed" in values else None
        if ("Active" in values and not int(values["Active"])) or (
            speed is not None and speed <= 0
        ):
            await self.hass.services.async_call(
                "humidifier", "turn_off", {ATTR_ENTITY_ID: ENTITY}, blocking=True,
            )
            return

        state = self.hass.states.get(ENTITY)
        if state is None or state.state in ("unknown", "unavailable"):
            _LOGGER.warning("Venta fan command skipped: humidifier unavailable")
            return

        if state.state == STATE_OFF:
            await self.hass.services.async_call(
                "humidifier", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True,
            )

        mode = None
        if "TargetFanState" in values:
            mode = "Auto" if int(values["TargetFanState"]) else "Manual"
        elif speed is not None:
            # A manual speed adjustment must leave automatic fan control.
            mode = "Manual"
        if mode:
            await self.hass.services.async_call(
                "humidifier", "set_mode",
                {ATTR_ENTITY_ID: ENTITY, "mode": mode}, blocking=True,
            )
        if speed is not None and speed > 0:
            level = str(max(1, min(5, round(speed / 20))))
            await self.hass.services.async_call(
                "select", "select_option",
                {ATTR_ENTITY_ID: FAN, "option": level}, blocking=True,
            )

    @callback
    def _venta_set_led(self, values: dict):
        if "On" in values:
            self.async_call_service(
                "switch",
                "turn_on" if bool(values["On"]) else "turn_off",
                {ATTR_ENTITY_ID: LED}, "LED power",
            )
        if "Brightness" in values:
            brightness = float(values["Brightness"])
            level = str(max(1, min(8, round(brightness * 8 / 100))))
            self.async_call_service(
                "select", "select_option",
                {ATTR_ENTITY_ID: BRIGHTNESS, "option": level}, "LED brightness",
            )

    @callback
    def _venta_update_extras(self):
        if not hasattr(self, "_venta_fan_active"):
            return
        states = self.hass.states
        hum = states.get(ENTITY)
        fan = states.get(FAN)
        led = states.get(LED)
        brightness = states.get(BRIGHTNESS)
        temp = states.get(TEMPERATURE)
        is_on = bool(hum and hum.state == STATE_ON)
        self._venta_fan_active.set_value(int(is_on))
        self._venta_auto_on.set_value(
            bool(is_on and hum.attributes.get("mode") == "Auto")
        )
        self._venta_fan_current.set_value(2 if is_on else 0)
        self._venta_fan_target.set_value(
            1 if hum and hum.attributes.get("mode") == "Auto" else 0
        )
        try:
            speed = max(0, min(100, int(fan.state) * 20))
        except (TypeError, ValueError, AttributeError):
            speed = 0
        self._venta_fan_speed.set_value(speed)
        self._venta_led_on.set_value(bool(led and led.state == STATE_ON))
        try:
            level = max(1, min(100, round(int(brightness.state) * 100 / 8)))
            self._venta_led_brightness.set_value(level)
        except (TypeError, ValueError, AttributeError):
            pass
        try:
            degrees = max(-40.0, min(100.0, float(temp.state)))
            self._venta_temperature.set_value(degrees)
        except (TypeError, ValueError, AttributeError):
            pass

def _venta_accessory_factory(
    hass: HomeAssistant,
    driver,
    name: str,
    entity_id: str,
    aid: int,
    config: dict,
):
    """Use the native HA class for every humidifier other than Venta.

    HomeKit's TYPES registry is global. A per-entity factory avoids changing
    accessory classes, characteristic handlers or AIDs for other humidifiers.
    The Venta class and its linked-service unique IDs remain unchanged.
    """
    cls = (
        VentaEnhancedHumidifier
        if entity_id == ENTITY
        else NativeHumidifierDehumidifier
    )
    return cls(hass, driver, name, entity_id, aid, config)


def _homekit_apis_compatible() -> bool:
    """Refuse to patch when required HA/PyHAP internals have changed."""
    return all(
        callable(getattr(owner, method, None))
        for owner, method in (
            (NativeHumidifierDehumidifier, "get_service"),
            (NativeHumidifierDehumidifier, "set_primary_service"),
            (NativeHumidifierDehumidifier, "add_preload_service"),
            (NativeHumidifierDehumidifier, "async_update_state"),
            (Characteristic, "override_properties"),
            (Service, "add_linked_service"),
        )
    )


@callback
def _reload_venta(hass: HomeAssistant):
    """Rebuild only Venta inside the existing bridge; all other AIDs survive."""
    async_dispatcher_send(
        hass, SIGNAL_RELOAD_ENTITIES.format(BRIDGE_ENTRY), (ENTITY,)
    )

async def _reload_when_bridge_ready(hass: HomeAssistant) -> None:
    """Do not dispatch a reload until HomeKit has initialized its bridge.

    HomeKit registers its signal before creating the HAP driver. Dispatching
    immediately on EVENT_HOMEASSISTANT_STARTED can raise AssertionError.
    """
    for _ in range(120):
        entry = hass.config_entries.async_get_entry(BRIDGE_ENTRY)
        bridge = getattr(getattr(entry, "runtime_data", None), "homekit", None)
        if (
            bridge is not None
            and bridge.status == STATUS_RUNNING
            and bridge.driver is not None
            and bridge.bridge is not None
        ):
            _reload_venta(hass)
            _LOGGER.info("Reloaded Venta after native HomeKit bridge became ready")
            return
        await asyncio.sleep(2)
    _LOGGER.warning("Venta HomeKit bridge not ready after 240 seconds; not reloading")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    global ENTITY, BRIDGE_ENTRY, FAN, LED, BRIGHTNESS, TEMPERATURE, HUMIDITY, EXTRA_ENTITIES
    values = config.get(DOMAIN)
    # No YAML is normal for a UI-configured installation; the config entry
    # is validated and set up separately. Existing seven-key YAML is unchanged.
    if values is None:
        return True
    names = ("humidifier_entity", "bridge_title", "fan_entity", "led_entity",
             "brightness_entity", "temperature_entity", "humidity_entity")
    if not isinstance(values, dict) or any(
        not isinstance(values.get(k), str) or not values[k].strip()
        for k in names
    ):
        _LOGGER.error("Venta: configuration.yaml must define all seven options")
        return False
    # YAML keeps title matching. Config entries also pin the exact bridge ID
    # so duplicate titles can never redirect a configured Venta accessory.
    bridge_id = values.get("bridge_entry_id")
    matching = [
        e for e in hass.config_entries.async_entries("homekit")
        if (e.entry_id == bridge_id if bridge_id else e.title == values["bridge_title"])
    ]
    if len(matching) != 1:
        _LOGGER.error("Venta: existing HomeKit bridge identity must match exactly")
        return False
    bridge = matching[0]
    if bridge.options.get("mode", "bridge") != "bridge":
        _LOGGER.error("Venta: entry must be a HomeKit bridge")
        return False
    bridge_filter = bridge.options.get("filter") or {}
    included = bridge_filter.get("include_entities") or []
    excluded = bridge_filter.get("exclude_entities") or []
    if (included and values["humidifier_entity"] not in included) or (
        values["humidifier_entity"] in excluded
    ):
        _LOGGER.error("Venta: humidifier must be included in existing HomeKit bridge")
        return False
    original = TYPES.get("HumidifierDehumidifier")
    if original is _venta_accessory_factory and hass.data.get(DOMAIN, {}).get("patched"):
        # Repeated setup is idempotent only for the same exact accessory and
        # bridge. Reject another config entry rather than switching globals.
        if ENTITY == values["humidifier_entity"] and BRIDGE_ENTRY == bridge.entry_id:
            return True
        _LOGGER.error("Venta: another accessory is already registered")
        return False
    if original is not NativeHumidifierDehumidifier:
        _LOGGER.error("Unexpected HomeKit registry: refusing to patch")
        return False
    if not _homekit_apis_compatible():
        _LOGGER.error("Incompatible HomeKit/PyHAP API: refusing to patch")
        return False
    # No mutable globals change until all singleton and API gates pass.
    ENTITY = values["humidifier_entity"]
    BRIDGE_ENTRY = bridge.entry_id
    FAN = values["fan_entity"]
    LED = values["led_entity"]
    BRIGHTNESS = values["brightness_entity"]
    TEMPERATURE = values["temperature_entity"]
    HUMIDITY = values["humidity_entity"]
    EXTRA_ENTITIES = (FAN, LED, BRIGHTNESS, TEMPERATURE)
    TYPES["HumidifierDehumidifier"] = _venta_accessory_factory
    hass.data[DOMAIN] = {"original": original, "patched": True}

    # Marketplace replaces this integration's files, not LocalTuya's template
    # picker directory. Keep only a known, unchanged copy synchronized.
    # Never modify LocalTuya device config entries or an edited template.
    try:
        template_state = await hass.async_add_executor_job(
            sync_managed_template, Path(hass.config.config_dir)
        )
        _LOGGER.info("Venta LocalTuya template synchronization: %s", template_state)
    except (OSError, RuntimeError, ValueError) as exc:
        _LOGGER.warning("Venta LocalTuya template synchronization skipped: %s", exc)

    @callback
    def manual_reload(_):
        _reload_venta(hass)

    # For explicit testing / reconnect, not full HomeKit or HA restart.
    hass.services.async_register(DOMAIN, "reload_venta", manual_reload)

    @callback
    def log_diagnostics(_):
        # Explicit, read-only request. Report only allow-listed statuses;
        # never log raw device state/attributes, entity IDs or pairing data.
        report = collect_diagnostics(
            hass,
            entity_ids={
                "humidifier": ENTITY,
                "fan": FAN,
                "led": LED,
                "brightness": BRIGHTNESS,
                "temperature": TEMPERATURE,
                "humidity": HUMIDITY,
            },
            bridge_entry_id=BRIDGE_ENTRY,
            home_assistant_version=HA_VERSION,
            integration_dir=Path(__file__).resolve().parent,
        )
        _LOGGER.info("Venta diagnostic status: %s", json.dumps(report, sort_keys=True))
        return report

    hass.services.async_register(
        DOMAIN, "log_diagnostics", log_diagnostics,
        supports_response=SupportsResponse.OPTIONAL,
    )

    if hass.is_running:
        hass.async_create_task(_reload_when_bridge_ready(hass))
    else:
        @callback
        def started(_):
            hass.async_create_task(_reload_when_bridge_ready(hass))
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, started)

    _LOGGER.info("Venta native HomeKit accessory extension registered")
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    """Set up one approved UI mapping without creating any HA entities.

    The legacy YAML bridge is authoritative until explicitly migrated in
    V120-03. A second entry may never take over the singleton HAP factory.
    """
    from .entity_discovery import DiscoveryError, validate_from_hass

    if hass.data.get(DOMAIN, {}).get("patched"):
        _LOGGER.error("Venta: existing YAML or UI setup must be migrated first")
        return False
    values = dict(entry.data)
    try:
        selections = {
            role: values.get(f"{role}_entity")
            for role in ("fan", "led", "brightness", "temperature", "humidity")
        }
        confirmed = frozenset(values.get("confirmed_unclassified", []))
        problems = validate_from_hass(
            hass, values.get("humidifier_entity"), selections,
            confirmed_unclassified=confirmed,
        )
    except (DiscoveryError, TypeError, ValueError):
        _LOGGER.error("Venta: saved entity mapping is no longer valid")
        return False
    if problems:
        _LOGGER.error("Venta: saved entity mapping changed; repair required")
        return False
    ok = await async_setup(hass, {DOMAIN: values})
    if ok and hass.data.get(DOMAIN, {}).get("patched"):
        hass.data[DOMAIN]["config_entry_id"] = entry.entry_id
    return ok


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    """Fail closed until HomeKit lifecycle-safe unload is implemented.

    Returning False requires a restart instead of leaving an existing HAP
    accessory bound to a different controller or accidentally re-pairing it.
    V120-04 will implement guarded unload/reconfigure with identity tests.
    """
    return not hass.data.get(DOMAIN, {}).get("patched")
