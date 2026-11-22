# Venta 1.2.0 — safe entity association (V120-02 preview)

**Source-only preview. This is not yet an installed setup wizard.** No change
to existing seven-key YAML installations, HomeKit pairing or LocalTuya config
entries is made by adding this module. The installed 1.0.4 release does not
include it, and the separate 1.0.5 maintenance candidate excludes it.

## Trust boundary

The future UI chooses an existing LocalTuya humidifier and obtains its
Home Assistant entity registry entry. Related entities are offered only if
all of these properties match the humidifier:

- Exact **device_id**, not name/area or substring of the entity ID
- Exact **config_entry_id**, not merely the same LocalTuya integration
- Platform localtuya, enabled and not hidden
- Correct HA entity domain: fan/brightness from select, LED from switch,
  temperature/humidity from sensor

For the temperature/humidity sensors, an explicit HA device_class or
original_device_class of temperature/humidity is accepted. A known but
different class (for example particulate matter, energy) is rejected.
An unclassified sensor is shown as needing separate manual verification; it is
never silently trusted.

**Select roles are never inferred from similar names:** fan speed and LED
brightness can both be select entities, so their choices always require human
confirmation. Even an unambiguous LED or classified sensor is shown only as
a suggestion, not automatically saved. A missing role blocks submission.

An entry that becomes disabled, moves to another device, disappears, or changes
platform between opening and submitting a form must be rejected by **re-reading
the entity registry on submit**.

## Code and test scope

- custom_components/venta_homekit_native/entity_discovery.py: read-only
  plan_from_entries, validate_selection, discover_from_hass and
  validate_from_hass; simple role-choice and error structures, no service calls,
  network requests, configuration writes or logs.
- tests/test_entity_discovery.py: synthetic multi-device, multi-config,
  disabled/hidden/PM2.5/unclassified and stale-registration regressions.
- scripts/ha_entity_registry_smoke.py: real Home Assistant 2026.11.1 and
  2026.11.2 entity-registry API imports, using synthetic fixtures and a network-
  disabled container.

**Not yet implemented:** UI entity selectors and confirmation screens,
config_flow, source YAML import, persistence of a config entry, options,
repair flow and a live HomeKit migration. Those are separate P03 roadmap
acceptance gates. This helper is only a security-critical building block.
No saved device IDs, LocalTuya local keys or pairing data should be placed in
test fixtures, logs or GitHub issues.

These checks cannot establish compatibility with unknown Venta models or
firmware. Keep the tested AW730 / Tuya LAN 3.4 scope until physical evidence
supports a wider claim.
