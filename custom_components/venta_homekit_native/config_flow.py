"""Safe, single-instance Venta setup from existing LocalTuya and HomeKit entities.

The flow never operates a device, creates HomeKit accessories, changes a bridge,
or silently guesses the five related entities. The registry is re-read on submit.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er

from . import DOMAIN
from .entity_discovery import (
    DiscoveryError,
    ROLES,
    discover_from_hass,
    validate_from_hass,
)


class VentaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the already-existing AW730 accessory, not a second bridge."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._humidifier: str | None = None
        self._bridge_id: str | None = None
        self._migration_snapshot: tuple[str, ...] | None = None

    def _choices(self) -> tuple[dict[str, str], dict[str, str]]:
        registry = er.async_get(self.hass)
        humidifiers = {
            entry.entity_id: entry.entity_id
            for entry in registry.entities.values()
            if isinstance(entry.entity_id, str)
            and entry.entity_id.startswith("humidifier.")
            and entry.platform == "localtuya"
            and entry.disabled_by is None
            and entry.hidden_by is None
            and bool(entry.device_id)
            and bool(entry.config_entry_id)
        }
        bridges = {
            entry.entry_id: entry.title
            for entry in self.hass.config_entries.async_entries("homekit")
            if entry.options.get("mode", "bridge") == "bridge"
        }
        return dict(sorted(humidifiers.items())), dict(sorted(bridges.items()))

    def _bridge(self) -> Any | None:
        """Look up by stable ID on every request; titles are not unique."""
        return next(
            (
                entry
                for entry in self.hass.config_entries.async_entries("homekit")
                if entry.entry_id == self._bridge_id
            ),
            None,
        )

    def _bridge_error(self) -> str | None:
        bridge = self._bridge()
        if bridge is None or bridge.options.get("mode", "bridge") != "bridge":
            return "bridge_unavailable"
        filters = bridge.options.get("filter") or {}
        includes = filters.get("include_entities") or []
        excludes = filters.get("exclude_entities") or []
        if (includes and self._humidifier not in includes) or (
            self._humidifier in excludes
        ):
            return "bridge_excludes_humidifier"
        return None

    def _already_installed(self) -> bool:
        """Never combine UI setup with the existing YAML-driven global patch."""
        return bool(
            self.hass.data.get(DOMAIN, {}).get("patched")
            or self._async_current_entries()
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Choose one LocalTuya humidifier and an existing HomeKit bridge."""
        # Interactive migration is distinct from a second installation.
        # This never writes YAML, unloads HomeKit, or starts a second bridge.
        if self.hass.data.get(DOMAIN, {}).get("legacy_yaml"):
            return await self.async_step_migrate_yaml(user_input)
        if self._already_installed():
            return self.async_abort(reason="single_instance_allowed")

        humidifiers, bridges = self._choices()
        if not humidifiers:
            return self.async_abort(reason="localtuya_humidifier_missing")
        if not bridges:
            return self.async_abort(reason="homekit_bridge_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            humidifier = user_input.get("humidifier_entity")
            bridge = user_input.get("bridge_entry_id")
            if humidifier not in humidifiers:
                errors["humidifier_entity"] = "invalid_humidifier"
            if bridge not in bridges:
                errors["bridge_entry_id"] = "bridge_unavailable"
            if not errors:
                self._humidifier = humidifier
                self._bridge_id = bridge
                if problem := self._bridge_error():
                    errors["bridge_entry_id"] = problem
                else:
                    try:
                        discover_from_hass(self.hass, humidifier)
                    except DiscoveryError:
                        errors["humidifier_entity"] = "invalid_humidifier"
                    else:
                        await self.async_set_unique_id(humidifier)
                        self._abort_if_unique_id_configured()
                        return await self.async_step_entities()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("humidifier_entity"): vol.In(humidifiers),
                vol.Required("bridge_entry_id"): vol.In(bridges),
            }),
            errors=errors,
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        """Require explicit role choices and reject changed registrations."""
        if self._already_installed():
            return self.async_abort(reason="single_instance_allowed")
        if not self._humidifier or not self._bridge_id:
            return await self.async_step_user()
        if problem := self._bridge_error():
            return self.async_abort(reason=problem)

        try:
            plan = discover_from_hass(self.hass, self._humidifier)
        except DiscoveryError:
            return self.async_abort(reason="localtuya_humidifier_missing")
        if not plan["can_submit"]:
            return self.async_abort(reason="required_entities_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            selections = {
                role: user_input.get(f"{role}_entity")
                for role in ROLES
            }
            confirmed = frozenset(
                role for role in ("temperature", "humidity")
                if user_input.get(f"confirm_{role}", False) is True
            )
            try:
                problems = validate_from_hass(
                    self.hass,
                    self._humidifier,
                    selections,
                    confirmed_unclassified=confirmed,
                )
            except DiscoveryError:
                return self.async_abort(reason="localtuya_humidifier_missing")

            errors = {
                f"{role}_entity": "invalid_entity"
                for role in ROLES
                if role in problems
            }
            if problems.get("_form") or problems.get("_confirmation"):
                errors["base"] = "invalid_entity"
            if not errors:
                if self._bridge_error():
                    return self.async_abort(reason="bridge_unavailable")
                if self._already_installed():
                    return self.async_abort(reason="single_instance_allowed")
                await self.async_set_unique_id(self._humidifier)
                self._abort_if_unique_id_configured()
                bridge = self._bridge()
                return self.async_create_entry(
                    title="Venta AW730",
                    data={
                        "humidifier_entity": self._humidifier,
                        "bridge_entry_id": self._bridge_id,
                        "bridge_title": bridge.title,
                        "confirmed_unclassified": sorted(confirmed),
                        **{
                            f"{role}_entity": selections[role]
                            for role in ROLES
                        },
                    },
                )

        schema: dict[Any, Any] = {
            vol.Required(f"{role}_entity"): vol.In(
                plan["roles"][role]["options"]
            )
            for role in ROLES
        }
        for role in ("temperature", "humidity"):
            if plan["roles"][role]["unclassified"]:
                schema[vol.Optional(f"confirm_{role}", default=False)] = bool

        return self.async_show_form(
            step_id="entities",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_import(self, user_input: dict[str, Any] | None = None):
        """Never silently migrate YAML through the automatic import source."""
        return self.async_abort(reason="interactive_yaml_migration_required")

    async def async_step_migrate_yaml(
        self, user_input: dict[str, Any] | None = None
    ):
        """Opt-in, restart-bound transfer of the existing seven YAML values.

        Creating the entry does NOT remove or disable the active YAML patch.
        The entry intentionally fails to set up until YAML is removed and HA
        restarted; rollback is simply restoring the original seven YAML keys.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        active = self.hass.data.get(DOMAIN, {})
        legacy = active.get("legacy_yaml")
        required = (
            "humidifier_entity", "bridge_title", "fan_entity", "led_entity",
            "brightness_entity", "temperature_entity", "humidity_entity",
            "bridge_entry_id",
        )
        if not active.get("patched") or not isinstance(legacy, dict) or any(
            not isinstance(legacy.get(key), str) or not legacy[key]
            for key in required
        ):
            return self.async_abort(reason="yaml_migration_unavailable")

        fingerprint = tuple(legacy[key] for key in required)
        if self._migration_snapshot is None:
            self._migration_snapshot = fingerprint
        elif fingerprint != self._migration_snapshot:
            return self.async_abort(reason="yaml_migration_unavailable")

        self._humidifier = legacy["humidifier_entity"]
        self._bridge_id = legacy["bridge_entry_id"]
        if self._bridge_error():
            return self.async_abort(reason="bridge_unavailable")

        try:
            plan = discover_from_hass(self.hass, self._humidifier)
        except DiscoveryError:
            return self.async_abort(reason="localtuya_humidifier_missing")
        if not plan["can_submit"]:
            return self.async_abort(reason="required_entities_missing")

        choices = {
            role: legacy[f"{role}_entity"] for role in ROLES
        }
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                user_input.get("confirm_backup") is not True
                or user_input.get("confirm_remove_yaml_and_restart") is not True
            ):
                errors["base"] = "yaml_migration_confirmation_required"
            else:
                confirmed = frozenset(
                    role for role in ("temperature", "humidity")
                    if user_input.get(f"confirm_{role}") is True
                )
                try:
                    problems = validate_from_hass(
                        self.hass, self._humidifier, choices,
                        confirmed_unclassified=confirmed,
                    )
                except DiscoveryError:
                    return self.async_abort(reason="localtuya_humidifier_missing")
                if problems:
                    errors["base"] = "yaml_migration_entities_changed"
                elif self._bridge_error():
                    # A stale confirmation cannot bind another HomeKit bridge.
                    return self.async_abort(reason="yaml_migration_unavailable")
                elif self._async_current_entries():
                    return self.async_abort(reason="single_instance_allowed")
                else:
                    await self.async_set_unique_id(self._humidifier)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Venta AW730",
                        data={
                            **{key: legacy[key] for key in required},
                            "confirmed_unclassified": sorted(confirmed),
                            "migration_from_yaml": True,
                        },
                    )

        schema: dict[Any, Any] = {
            vol.Required("confirm_backup", default=False): bool,
            vol.Required("confirm_remove_yaml_and_restart", default=False): bool,
        }
        for role in ("temperature", "humidity"):
            if choices[role] in plan["roles"][role]["unclassified"]:
                schema[vol.Required(f"confirm_{role}", default=False)] = bool
        return self.async_show_form(
            step_id="migrate_yaml",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
