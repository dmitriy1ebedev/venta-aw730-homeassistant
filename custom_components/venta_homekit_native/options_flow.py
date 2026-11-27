"""Non-disruptive Venta options review; changes remain proposals until reconfigure.

Editing options does not alter the active HomeKit bridge, bound entity globals,
LocalTuya configuration or Apple Home pairing. The separate reconfigure flow
must revalidate an explicit proposal and requires an approved HA restart.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er

from . import DOMAIN
from .binding_review import (
    BRIDGE,
    ROLE_FIELDS,
    SOURCE,
    bridge_choices,
    mapping_changed,
    review_plan,
    review_proposal,
)
from .entity_discovery import DiscoveryError, ROLES
from .service_advisories import SERVICE_ROLES, eligible_service_sensor_ids

PROPOSAL = "review_proposal"
SOURCE_SNAPSHOT = "review_source"


def binding_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    """Pin the source config-entry mapping so a stale review cannot apply."""
    keys = (SOURCE, BRIDGE, *ROLE_FIELDS, "confirmed_unclassified")
    return {key: values.get(key) for key in keys}


class VentaOptionsFlow(config_entries.OptionsFlow):
    """Choose and validate a proposal only; no device operations or reload."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Require explicit choices and confirmation before saving a proposal."""
        entry = self.config_entry
        active = self.hass.data.get(DOMAIN, {})
        if active.get("patched") and active.get("config_entry_id") != entry.entry_id:
            return self.async_abort(reason="yaml_or_other_owner")

        current = dict(entry.data)
        try:
            plan = review_plan(self.hass, current)
        except (DiscoveryError, TypeError, ValueError):
            return self.async_abort(reason="localtuya_humidifier_missing")
        if not plan["can_submit"]:
            return self.async_abort(reason="required_entities_missing")

        bridges = bridge_choices(self.hass)
        if not bridges:
            return self.async_abort(reason="bridge_unavailable")
        available_service_sensors = eligible_service_sensor_ids(
            er.async_get(self.hass), current.get("humidifier_entity")
        )
        stored_service_map = entry.options.get("service_advisory_entities", {})
        if not isinstance(stored_service_map, dict):
            stored_service_map = {}
        stored_native_sensors = entry.options.get("native_sensor_entities", {})
        if not isinstance(stored_native_sensors, dict):
            stored_native_sensors = {}
        errors: dict[str, str] = {}
        if user_input is not None:
            native_ui = user_input.get("native_device_ui", entry.options.get("native_device_ui", False))
            if type(native_ui) is not bool:
                errors["base"] = "native_export_review_required"
            elif native_ui:
                if user_input.get("confirm_native_device_ui") is not True:
                    errors["base"] = "native_export_review_required"
                else:
                    from .export_guard import export_blockers
                    try:
                        if export_blockers(self.hass, entry.entry_id):
                            errors["base"] = "native_export_review_required"
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        errors["base"] = "native_export_review_required"
            requested_service_map = {}
            for role in SERVICE_ROLES:
                field = f"{role}_entity"
                selected = user_input.get(field, stored_service_map.get(role, ""))
                if not isinstance(selected, str) or (
                    selected and selected not in available_service_sensors
                ):
                    errors[field] = "invalid_entity"
                elif selected:
                    requested_service_map[role] = selected
            if len(requested_service_map) != len(set(requested_service_map.values())):
                errors["base"] = "distinct_service_entities_required"
            if (
                not errors
                and requested_service_map != stored_service_map
                and requested_service_map
                and user_input.get("confirm_service_monitoring") is not True
            ):
                errors["base"] = "service_monitoring_confirmation_required"
            selections = {
                role: user_input.get(f"{role}_entity")
                for role in ROLES
            }
            confirmed = frozenset(
                role for role in ("temperature", "humidity")
                if user_input.get(f"confirm_{role}") is True
                and selections[role] in plan["roles"][role]["unclassified"]
            )
            review_errors, proposal = review_proposal(
                self.hass, current, user_input.get(BRIDGE), selections,
                confirmed_unclassified=confirmed,
            )
            errors.update(review_errors)
            if not errors and user_input.get("confirm_staging") is not True:
                errors["base"] = "staging_confirmation_required"
            native_sensors = {}
            sensor_pins = {}
            if not errors and native_ui:
                from .device_binding import BindingError, resolve_source
                from .native_control import ControlError
                from .native_sensor_values import sensor_fingerprint

                native_sensors = dict(requested_service_map)
                pm25 = user_input.get("pm25_entity", stored_native_sensors.get("pm25", ""))
                if not isinstance(pm25, str) or (pm25 and pm25 not in available_service_sensors):
                    errors["pm25_entity"] = "invalid_entity"
                elif pm25:
                    native_sensors["pm25"] = pm25
                try:
                    registry = er.async_get(self.hass)
                    source = registry.async_get(current[SOURCE])
                    identity = resolve_source(self.hass, current[SOURCE], expected=current.get("native_device_identity"))
                    if (len(set(native_sensors.values())) != len(native_sensors)
                            or set(native_sensors.values()) & set(selections.values())):
                        raise ControlError("duplicate_sensor")
                    sensor_pins = {role: sensor_fingerprint(source, registry.async_get(entity_id), role, identity)
                                   for role, entity_id in native_sensors.items()}
                except (BindingError, ControlError, AttributeError, RuntimeError, TypeError, ValueError):
                    errors["base"] = "native_sensor_review_required"
            if not errors and proposal is not None:
                options = dict(entry.options)
                if mapping_changed(current, proposal):
                    options[PROPOSAL] = proposal
                    options[SOURCE_SNAPSHOT] = binding_snapshot(current)
                else:
                    # Explicitly discards only our own obsolete review.
                    options.pop(PROPOSAL, None)
                    options.pop(SOURCE_SNAPSHOT, None)
                if requested_service_map:
                    options["service_advisory_entities"] = requested_service_map
                else:
                    options.pop("service_advisory_entities", None)
                if native_ui:
                    options["native_device_ui"] = True
                    options["native_sensor_entities"] = native_sensors
                    options["native_sensor_pins"] = sensor_pins
                else:
                    options.pop("native_device_ui", None)
                    options.pop("native_sensor_entities", None)
                    options.pop("native_sensor_pins", None)
                return self.async_create_entry(title="", data=options)

        def required_choice(key: str, choices: Any) -> Any:
            original = current.get(key)
            if original in choices:
                return vol.Required(key, default=original)
            return vol.Required(key)

        schema: dict[Any, Any] = {
            required_choice(BRIDGE, bridges): vol.In(bridges),
        }
        for role in ROLES:
            field = f"{role}_entity"
            options = plan["roles"][role]["options"]
            schema[required_choice(field, options)] = vol.In(options)
        saved_confirmed = set(current.get("confirmed_unclassified", []))
        for role in ("temperature", "humidity"):
            if plan["roles"][role]["unclassified"]:
                schema[vol.Optional(
                    f"confirm_{role}", default=role in saved_confirmed,
                )] = bool
        for role in SERVICE_ROLES:
            field = f"{role}_entity"
            schema[vol.Optional(
                field, default=stored_service_map.get(role, "")
            )] = vol.In({
                "": "Disabled",
                **{entity_id: entity_id for entity_id in available_service_sensors},
            })
        schema[vol.Optional("confirm_service_monitoring", default=False)] = bool
        schema[vol.Optional("native_device_ui", default=entry.options.get("native_device_ui") is True)] = bool
        schema[vol.Optional("confirm_native_device_ui", default=False)] = bool
        schema[vol.Optional("pm25_entity", default=stored_native_sensors.get("pm25", ""))] = vol.In({
            "": "Disabled",
            **{entity_id: entity_id for entity_id in available_service_sensors},
        })
        schema[vol.Required("confirm_staging", default=False)] = bool
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema), errors=errors,
        )
