"""Non-disruptive Venta options review; changes remain proposals until reconfigure.

Editing options does not alter the active HomeKit bridge, bound entity globals,
LocalTuya configuration or Apple Home pairing. The separate reconfigure flow
must revalidate an explicit proposal and requires an approved HA restart.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

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
        errors: dict[str, str] = {}
        if user_input is not None:
            selections = {
                role: user_input.get(f"{role}_entity")
                for role in ROLES
            }
            confirmed = frozenset(
                role for role in ("temperature", "humidity")
                if user_input.get(f"confirm_{role}") is True
                and selections[role] in plan["roles"][role]["unclassified"]
            )
            errors, proposal = review_proposal(
                self.hass, current, user_input.get(BRIDGE), selections,
                confirmed_unclassified=confirmed,
            )
            if not errors and user_input.get("confirm_staging") is not True:
                errors["base"] = "staging_confirmation_required"
            if not errors and proposal is not None:
                options = dict(entry.options)
                if mapping_changed(current, proposal):
                    options[PROPOSAL] = proposal
                    options[SOURCE_SNAPSHOT] = binding_snapshot(current)
                else:
                    # Explicitly discards only our own obsolete review.
                    options.pop(PROPOSAL, None)
                    options.pop(SOURCE_SNAPSHOT, None)
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
        schema[vol.Required("confirm_staging", default=False)] = bool
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema), errors=errors,
        )
