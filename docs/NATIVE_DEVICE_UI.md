# Venta 1.4.0 — native device card (P06, development candidate)

This document describes unreleased development code. It is not a claim that
the new entities are installed on any physical washer.

## Ownership and controls

LocalTuya remains the only LAN transport. HA 2026.8+ uses single-config-entry
device ownership; Venta registers a distinct logical device with its own
identifiers, never the source MAC, LocalTuya device ID or existing entity
registry rows. The primary source identity and all six control-role identities
are pinned. A changed source under an unchanged entity ID is rejected.

The new UI projections use HA's standard humidifier, fan, light and sensor
platforms. They do not replace the original LocalTuya entities. Power, target
humidity (30–70%), Auto/Manual/Sleep, five fan levels and eight brightness
levels delegate to the original services with source identity and readback
checks. Fan speed above zero selects Manual; zero powers the washer off.
A partial multi-step command is reported as an error if later readback fails;
no speculative compensating hardware command is issued.

Temperature and RH come from the already confirmed source roles. Optional
PM2.5, water level and filter/cleaning/service intervals require an explicit
mapping in Options. Numeric values and units are checked, unavailable or
invalid data is not displayed as zero. Temperature is normalized to Celsius
before HA's normal unit conversion. No reset button is created. The existing
opt-in service-advisory monitor is not duplicated.

## Safe activation and rollback

1. Preserve and verify the existing HA backup (including pairing and recorder
   data). Note the current LocalTuya entity IDs and existing bridge/export
   filters. Do not copy production data into a public report or test fixture.
2. If Venta is already managed by a UI config entry, retain it. If Venta is
   configured in YAML, use the existing interactive **Migrate YAML** wizard
   with the exact source and bridge. Do not delete YAML until the backup and
   migration proposal are verified. The running YAML owner remains
   authoritative; remove only its block and restart manually when approved.
3. In the Venta entry's Options, review the existing roles, choose any
   optional sensors, check **Native Venta controls** and explicitly confirm
   the export review. Saving stages settings. Restart manually after backup.
4. Only explicit entity allowlists (or the supported Yaha label filter) are
   admitted. Broad, missing, YAML-only or unknown export filters block native
   projections instead of altering another integration. Do not add the new
   Venta projections to Apple Home or Alice; keep the original physical
   source exported once. A later manual widening of another integration's
   filters is outside automatic export control; review it before changing it.
5. A deliberate same-device role change is applied only through the existing
   reconfigure wizard after confirmation. The source pin is never reset and
   unchanged roles must retain their pins. Replacing an optional sensor under
   the same entity ID requires clearing its mapping and explicitly reviewing
   it again. A foreign or missing source is not guessed.
6. If activation fails, the existing HAP mapping stays active. Disable the
   native controls in Options and restart manually, or restore the verified
   pre-change backup. Do not remove pairing state, reset the washer or delete
   original LocalTuya entities. Native entity history is separate; existing
   automations and history continue to refer to original IDs.

## Русский

LocalTuya остаётся транспортом. В настройках Venta появится отдельное
логическое устройство с нативными сущностями. Старые сущности сохраняются.
Для YAML сначала используйте существующий мастер миграции, резервную копию и
ручной перезапуск. Затем в параметрах Venta включите собственные элементы
управления, подтвердите проверку явных фильтров HomeKit/Яндекс и выберите
дополнительные датчики. Не экспортируйте вторую копию мойки. Если фильтры
не подтверждены, новые сущности не создаются; существующий мост сохраняется.
Неподтверждённые счётчики и PM2.5 не угадываются, сбросы не выполняются.

CI uses only isolated Home Assistant and synthetic source state. The actual
HA platform smoke registers ten native entities, exercises the native HA
service registry and checks the simulated LocalTuya readback. A separate
stock frontend gate replays that successful run's synthetic device/entity
registry and state snapshot in a clean HA instance with inert integration
stubs, then navigates from the standard integration page to its device card
at 1280 px and 390 px. It verifies all ten entity rows and viewport bounds.
This is stock UI rendering evidence, not a browser-to-hardware command test.
The live cutover and physical readback remain separate gates.
