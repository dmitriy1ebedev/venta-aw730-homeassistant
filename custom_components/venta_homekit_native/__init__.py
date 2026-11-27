"""Extend *only* the existing Venta HomeKit bridge accessory.

Do not start a new HAP server, change pairing, or modify any other entity.
Uses Home Assistant's own HomeKit HomeAccessory and bridge lifecycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path

from homeassistant.const import __version__ as HA_VERSION
from .diagnostics import collect_diagnostics
from .service_advisories import ServiceAdvisoryMonitor

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
from .model_profiles import AW730

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


def _homekit_number(value, minimum: float, maximum: float) -> float | None:
    """Validate a HomeKit number before issuing any physical command."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


def _homekit_binary(value) -> int | None:
    if isinstance(value, bool):
        return int(value)
    number = _homekit_number(value, 0, 1)
    return int(number) if number in (0, 1) else None


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
            choice = _homekit_binary(values["TargetHumidifierDehumidifierState"])
            if choice is None:
                _LOGGER.warning("Venta: invalid humidifier target choice")
                return
            self.hass.async_create_task(self._venta_apply_target(choice))
            self.char_target_humidifier_dehumidifier.set_value(choice)
            values = {k: v for k, v in values.items()
                      if k != "TargetHumidifierDehumidifierState"}
        if values:
            super()._set_chars(values)

    async def _venta_apply_target(self, choice: int):
        choice = _homekit_binary(choice)
        if choice is None:
            return
        state = self.hass.states.get(ENTITY)
        if state is None or state.state not in (STATE_ON, STATE_OFF):
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
        enable = _homekit_binary(values["On"])
        if enable is not None:
            self.hass.async_create_task(self._venta_apply_auto_toggle(bool(enable)))

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
        # Check all supplied characteristics before the first service call.
        speed = _homekit_number(values["RotationSpeed"], 0, 100) if "RotationSpeed" in values else None
        active = _homekit_binary(values["Active"]) if "Active" in values else None
        target = _homekit_binary(values["TargetFanState"]) if "TargetFanState" in values else None
        if any(key in values and value is None for key, value in (
            ("RotationSpeed", speed), ("Active", active), ("TargetFanState", target),
        )) or not any(key in values for key in ("RotationSpeed", "Active", "TargetFanState")):
            _LOGGER.warning("Venta: invalid fan command")
            return
        state = self.hass.states.get(ENTITY)
        if state is None or state.state not in (STATE_ON, STATE_OFF):
            _LOGGER.warning("Venta fan command skipped: humidifier unavailable")
            return
        if active == 0 or (speed is not None and speed == 0):
            await self.hass.services.async_call(
                "humidifier", "turn_off", {ATTR_ENTITY_ID: ENTITY}, blocking=True,
            )
            return

        if state.state == STATE_OFF:
            await self.hass.services.async_call(
                "humidifier", "turn_on", {ATTR_ENTITY_ID: ENTITY}, blocking=True,
            )

        mode = None
        if target is not None:
            mode = "Auto" if target else "Manual"
        elif speed is not None:
            # A manual speed adjustment must leave automatic fan control.
            mode = "Manual"
        if mode:
            await self.hass.services.async_call(
                "humidifier", "set_mode",
                {ATTR_ENTITY_ID: ENTITY, "mode": mode}, blocking=True,
            )
        # Explicit Auto wins over a stale positive slider value in the same
        # HAP write; do not dispatch contradictory manual speed alongside it.
        if speed is not None and speed > 0 and target != 1:
            level = str(max(1, min(AW730.fan_levels, round(speed / AW730.fan_step_percent))))
            await self.hass.services.async_call(
                "select", "select_option",
                {ATTR_ENTITY_ID: FAN, "option": level}, blocking=True,
            )

    @callback
    def _venta_set_led(self, values: dict):
        on = _homekit_binary(values["On"]) if "On" in values else None
        brightness = _homekit_number(values["Brightness"], 0, 100) if "Brightness" in values else None
        if ("On" in values and on is None) or ("Brightness" in values and brightness is None):
            _LOGGER.warning("Venta: invalid LED command")
            return
        if on is not None:
            self.async_call_service(
                "switch",
                "turn_on" if on else "turn_off",
                {ATTR_ENTITY_ID: LED}, "LED power",
            )
        if brightness is not None:
            level = str(max(1, min(AW730.brightness_levels, round(brightness * AW730.brightness_levels / 100))))
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
            speed = max(0, min(100, int(fan.state) * AW730.fan_step_percent))
        except (TypeError, ValueError, AttributeError):
            speed = 0
        self._venta_fan_speed.set_value(speed)
        self._venta_led_on.set_value(bool(led and led.state == STATE_ON))
        try:
            level = max(1, min(100, round(int(brightness.state) * 100 / AW730.brightness_levels)))
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
        if (
            ENTITY == values["humidifier_entity"]
            and BRIDGE_ENTRY == bridge.entry_id
            and FAN == values["fan_entity"]
            and LED == values["led_entity"]
            and BRIGHTNESS == values["brightness_entity"]
            and TEMPERATURE == values["temperature_entity"]
            and HUMIDITY == values["humidity_entity"]
        ):
            return True
        _LOGGER.error("Venta: existing accessory binding differs; refusing to retarget")
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
    if not values.get("migration_from_yaml"):
        # Preserve a read-only, exact in-memory migration proposal. YAML owns
        # the active accessory until the owner removes YAML and restarts HA.
        # The stable bridge ID prevents title collisions after migration.
        hass.data[DOMAIN]["legacy_yaml"] = {
            key: values[key] for key in names
        }
        hass.data[DOMAIN]["legacy_yaml"]["bridge_entry_id"] = bridge.entry_id

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

    # Opt-in service monitoring. Never guess LocalTuya entity IDs or alter
    # existing YAML/registry bindings. The owner explicitly maps each sensor.
    sensor_roles = ("water_level", "filter_days", "cleaning_days", "service_days")
    sensor_entities = {}
    for role in sensor_roles:
        entity_id = values.get(role + "_entity")
        if entity_id is None:
            continue
        try:
            sensor_entities[role] = cv.entity_id(entity_id)
        except (vol.Invalid, ValueError, TypeError):
            _LOGGER.warning("Venta: invalid service sensor mapping for %s", role)
    if sensor_entities and not hass.data[DOMAIN].get("service_monitor"):
        monitor = ServiceAdvisoryMonitor(hass, ENTITY, sensor_entities)
        hass.data[DOMAIN]["service_monitor"] = monitor
        watched = (ENTITY, *sensor_entities.values())

        @callback
        def on_service_state_change(event: Event):
            monitor.update(event.data.get("entity_id"))

        unsub = async_track_state_change_event(
            hass, watched, on_service_state_change,
            job_type=HassJobType.Callback,
        )
        hass.data[DOMAIN]["service_monitor_unsub"] = unsub
        # First sample only establishes a baseline; no startup alarm.
        monitor.update()


    if hass.is_running:
        hass.async_create_task(_reload_when_bridge_ready(hass))
    else:
        @callback
        def started(_):
            hass.async_create_task(_reload_when_bridge_ready(hass))
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, started)

    _LOGGER.info("Venta native HomeKit accessory extension registered")
    return True


def _binding_issue_id(entry) -> str:
    """Stable issue per config entry; no device identifiers or secrets."""
    return f"binding_{entry.entry_id}"


def _report_binding_issue(hass: HomeAssistant, entry) -> None:
    """Surface missing LocalTuya mappings in HA Repairs, never auto-repair."""
    try:
        from homeassistant.helpers import issue_registry as ir

        ir.async_create_issue(
            hass, DOMAIN, _binding_issue_id(entry),
            config_entry_id=entry.entry_id,
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="binding_unavailable",
        )
    except (ImportError, RuntimeError, ValueError, AttributeError):
        # Repairs metadata must never prevent HomeKit's fail-closed return.
        _LOGGER.warning("Venta binding review could not register a repair issue")


def _clear_binding_issue(hass: HomeAssistant, entry) -> None:
    """Remove only our own resolved issue after successful binding setup."""
    try:
        from homeassistant.helpers import issue_registry as ir

        ir.async_delete_issue(hass, DOMAIN, _binding_issue_id(entry))
    except (ImportError, RuntimeError, ValueError, AttributeError):
        _LOGGER.warning("Venta binding issue cleanup was unavailable")


def _setup_logical_device(hass: HomeAssistant, entry, entity_id: str) -> None:
    """Card registration is isolated from the working HomeKit accessory."""
    active = hass.data[DOMAIN]
    active.pop("native_device", None)
    active.pop("native_control", None)
    active.pop("native_sensors", None)
    if getattr(entry, "domain", None) != DOMAIN:
        return
    from .device_binding import BindingError, register_logical_device
    from homeassistant.exceptions import HomeAssistantError
    try:
        identity, device_id = register_logical_device(hass, entry, entity_id)
    except (BindingError, HomeAssistantError, AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        # Do not log registry IDs, credentials or arbitrary exception messages.
        # Incompatible/missing sources leave only the pre-existing bridge active.
        _LOGGER.warning("Venta: native device registration unavailable; existing bridge retained")
        return
    active["native_device"] = {"identity": identity, "device_id": device_id}
    # Prepare the pinned controller before any native UI platform is forwarded.
    from .native_control import ControlError, NativeControl

    roles = {role: entry.data.get(f"{role}_entity") for role in (
        "humidifier", "fan", "led", "brightness", "temperature", "humidity",
    )}
    expected_roles = entry.data.get("native_role_identities")
    try:
        controller = NativeControl(hass, identity, roles, expected_roles=expected_roles)
        if expected_roles is None:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, "native_role_identities": controller.role_identities.copy()},
            )
            if entry.data.get("native_role_identities") != controller.role_identities:
                raise ControlError("role_pin_not_saved")
    except (ControlError, HomeAssistantError, AttributeError, RuntimeError, TypeError, ValueError):
        _LOGGER.warning("Venta: native controls unavailable; existing bridge retained")
        return
    active["native_control"] = controller
    from .native_sensor_values import NativeSensors

    try:
        options = getattr(entry, "options", {})
        active["native_sensors"] = NativeSensors(
            controller, options.get("native_sensor_entities", {}),
            expected=options.get("native_sensor_pins", {}),
        )
    except (ControlError, AttributeError, RuntimeError, TypeError, ValueError):
        _LOGGER.warning("Venta: optional native sensor mappings unavailable")


async def _setup_native_platforms(hass: HomeAssistant, entry) -> None:
    """Forward standard HA platforms only after explicit, verified opt-in."""
    active = hass.data[DOMAIN]
    if active.get("native_ui_platforms_loaded"):
        return
    if (getattr(entry, "options", {}).get("native_device_ui") is not True
            or active.get("native_control") is None):
        return
    from homeassistant.const import Platform
    from homeassistant.exceptions import HomeAssistantError
    from .export_guard import export_blockers

    platforms = [Platform.HUMIDIFIER, Platform.FAN, Platform.LIGHT, Platform.SENSOR]
    try:
        if export_blockers(hass, entry.entry_id):
            _LOGGER.warning("Venta: native UI requires review of HomeKit/Yaha exports")
            return
        active["native_ui_enabled"] = True
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
    except (HomeAssistantError, AttributeError, RuntimeError, TypeError, ValueError):
        active["native_ui_enabled"] = False
        _LOGGER.warning("Venta: native UI setup failed; existing bridge retained")
        try:
            await hass.config_entries.async_unload_platforms(entry, platforms)
        except (HomeAssistantError, AttributeError, RuntimeError, TypeError, ValueError):
            _LOGGER.warning("Venta: native UI cleanup requires a safe restart")
        return
    active["native_ui_platforms_loaded"] = True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    """Set up one approved UI mapping and its separate logical device.

    The legacy YAML bridge is authoritative until explicitly migrated in
    V120-03. A second entry may never take over the singleton HAP factory.
    """
    from .entity_discovery import DiscoveryError, validate_from_hass

    active = hass.data.get(DOMAIN, {})
    if active.get("patched") and active.get("config_entry_id") != entry.entry_id:
        _LOGGER.error("Venta: existing YAML or another UI entry owns the HomeKit patch")
        return False
    values = dict(entry.data)
    # Registry identity is metadata, not part of the existing HAP mapping.
    values.pop("native_device_identity", None)
    values.pop("native_role_identities", None)
    # Service advisories are an explicit UI option, staged without a live
    # HomeKit reload. Revalidate registry ownership at the next safe setup.
    advisory_options = getattr(entry, "options", {}).get("service_advisory_entities")
    if advisory_options:
        from homeassistant.helpers import entity_registry as er
        from .service_advisories import validated_service_entities

        valid = validated_service_entities(
            er.async_get(hass), values.get("humidifier_entity"), advisory_options,
        )
        if len(valid) != len(advisory_options):
            _LOGGER.warning("Venta: stale service sensor mappings suppressed")
        for role, entity_id in valid.items():
            values[f"{role}_entity"] = entity_id
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
        _report_binding_issue(hass, entry)
        return False
    if problems:
        _LOGGER.error("Venta: saved entity mapping changed; repair required")
        _report_binding_issue(hass, entry)
        return False
    if active.get("patched"):
        # HA can request setup again for the same config entry. Never add a
        # second listener, registration or HomeKit accessory, and never accept
        # changed mappings in place: those need guarded reload/migration.
        if active.get("config_entry_data") == values:
            if not active.get("native_ui_platforms_loaded"):
                _setup_logical_device(hass, entry, values["humidifier_entity"])
                await _setup_native_platforms(hass, entry)
            _clear_binding_issue(hass, entry)
            return True
        _LOGGER.error("Venta: saved UI mapping differs from the active binding")
        return False
    ok = await async_setup(hass, {DOMAIN: values})
    if ok and hass.data.get(DOMAIN, {}).get("patched"):
        hass.data[DOMAIN]["config_entry_id"] = entry.entry_id
        hass.data[DOMAIN]["config_entry_data"] = values.copy()
        _setup_logical_device(hass, entry, values["humidifier_entity"])
        await _setup_native_platforms(hass, entry)
        _clear_binding_issue(hass, entry)
    elif not ok:
        _report_binding_issue(hass, entry)
    return ok


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    """Fail closed until HomeKit lifecycle-safe unload is implemented.

    Returning False requires a restart instead of leaving an existing HAP
    accessory bound to a different controller or accidentally re-pairing it.
    V120-04 will implement guarded unload/reconfigure with identity tests.
    """
    return not hass.data.get(DOMAIN, {}).get("patched")
