# Venta 1.2.0 — safe entity association (V120-02 preview)

**Released in Venta 1.2.0.** The config flow combines read-only discovery with explicit bridge and role selection. The historical canary retained the seven-key YAML installation and the original bridge; production UI cutover remains untested. See [release evidence](RELEASE_1_2_0.md).

## Trust boundary

The UI chooses an existing LocalTuya humidifier and obtains its
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

**V120-03 stacked candidate:** interactive, owner-confirmed YAML transfer
with pinned HomeKit bridge ID, an explicit backup acknowledgement and a
restart-bound rollback path. See [YAML migration](YAML_MIGRATION.md).
Automated `SOURCE_IMPORT` is rejected rather than silently creating a new
bridge or duplicate entry. Synthetic migration tests are not a live HA
restore test.

**V120-04 stacked candidate:** Options reviews and stores an inert proposal;
Reconfigure can save validated same-bridge roles only with explicit backup and
restart acknowledgements; Repairs verifies restored original bindings without
guessing entities, restarting HA or resetting HomeKit. See
[Options and Repairs](OPTIONS_AND_REPAIRS.md). New issues contain only a
fixed reason and a config-entry reference, never physical device credentials.

**Acceptance scope:** V120-03 and V120-04 isolated regressions and the 1.2.0 operational canary are recorded in ROADMAP. Safe live UI cutover and live unload still require separate verification. A green synthetic smoke does not authorize rollout.
No saved device IDs, LocalTuya local keys or pairing data should be placed in
test fixtures, logs or GitHub issues.

These checks cannot establish compatibility with unknown Venta models or
firmware. Keep the tested AW730 / Tuya LAN 3.4 scope until physical evidence
supports a wider claim.
