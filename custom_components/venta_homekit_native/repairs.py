"""Explicit, read-only Home Assistant repair flow for a lost Venta binding.

The repair flow only checks whether the *saved* LocalTuya roles and existing
HomeKit bridge are available again. It never guesses replacements, reloads a
bridge, changes entities or triggers an Apple Home pairing operation.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow

from . import DOMAIN
from .binding_review import BRIDGE, review_proposal
from .entity_discovery import ROLES


class VentaBindingRepairFlow(RepairsFlow):
    """Complete a repair only when all original references are valid again."""

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or getattr(entry, "domain", None) != DOMAIN:
            return self.async_abort(reason="entry_missing")

        active = self.hass.data.get(DOMAIN, {})
        if active.get("patched") and active.get("config_entry_id") != entry.entry_id:
            return self.async_abort(reason="yaml_or_other_owner")

        values = dict(entry.data)
        mapping = {role: values.get(f"{role}_entity") for role in ROLES}
        try:
            confirmed = frozenset(values.get("confirmed_unclassified", []))
            problems, refreshed = review_proposal(
                self.hass, values, values.get(BRIDGE), mapping,
                confirmed_unclassified=confirmed,
            )
        except (TypeError, ValueError):
            problems, refreshed = {"base": "invalid_entity"}, None

        if problems or refreshed is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({vol.Required("confirm_review", default=False): bool}),
                errors={"base": "binding_not_restored"},
            )
        if user_input is not None:
            if user_input.get("confirm_review") is not True:
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema({vol.Required("confirm_review", default=False): bool}),
                    errors={"base": "review_confirmation_required"},
                )
            # HA removes this repair issue after confirmation. It does not
            # change the stored mapping or reload the HomeKit bridge.
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("confirm_review", default=False): bool}),
        )


async def async_create_fix_flow(
    hass: Any,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create only a fix flow for a registered Venta config-entry issue."""
    if (
        not issue_id.startswith("binding_")
        or not isinstance(data, dict)
        or not isinstance(data.get("entry_id"), str)
        or issue_id != "binding_" + data["entry_id"]
    ):
        raise ValueError("unsupported_repair_issue")
    return VentaBindingRepairFlow(data["entry_id"])
