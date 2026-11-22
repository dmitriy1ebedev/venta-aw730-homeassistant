# Venta 1.2.0 — safe entity association (V120-02 preview)

**Development branch only; not installed or accepted for release.** The
P03.1 config flow now combines this read-only discovery with explicit bridge
and role selection. The existing seven-key YAML installation, HomeKit pairing,
and LocalTuya configuration remain unchanged. The installed 1.0.4 and the
separate 1.0.5 maintenance release do not include this candidate. It must pass
disposable Home Assistant runtime acceptance before any real installation.

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

**P03.1 worktree candidate:** config_flow.py provides source/bridge selectors,
explicit role confirmation, config-entry persistence, duplicate prevention and
revalidation at submit and setup. Replaying the same config entry must not
register listeners twice; a different entry or changed role mapping must fail
closed without retargeting the running HomeKit accessory. tests/test_config_flow.py
and tests/test_config_entry_lifecycle.py cover these invariants off-device.
The isolated HA 2026.11.1/2026.11.2 workflow additionally runs both the real
ConfigFlow smoke (scripts/ha_config_flow_smoke.py) and the real integration's
setup_entry/replay smoke (scripts/ha_config_entry_setup_smoke.py). Both use
in-memory fake registries with no HomeKit server or LocalTuya connection.

**Still pending:** YAML import and migration (P03.3), options/reconfigure/repairs
(P03.4), safe live unload, complete disposable runtime acceptance and an
owner-approved production canary (P03.5). No live HomeKit migration is
performed here. A green synthetic smoke does not authorize production rollout.
No saved device IDs, LocalTuya local keys or pairing data should be placed in
test fixtures, logs or GitHub issues.

These checks cannot establish compatibility with unknown Venta models or
firmware. Keep the tested AW730 / Tuya LAN 3.4 scope until physical evidence
supports a wider claim.
