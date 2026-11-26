# Architecture

Venta AW730 --(Tuya LAN 3.4 / LocalTuya)--> Home Assistant humidifier
        -> venta_homekit_native -> existing HomeKit Bridge -> Apple Home / Siri

Optional: HA humidifier -> Yaha Cloud -> Yandex Smart Home / Alice

See [cross-platform command and acceptance contract](PLATFORM_ACCEPTANCE.md) for the 1.3.0 candidate and separately required physical readback.

Marketplace manages `custom_components/venta_homekit_native/`, not LocalTuya's files.
This integration bundles `templates/venta_aw730.yaml` and calls
`sync_managed_template` once during its Home Assistant setup. The synchronization
copies a missing template and updates an unchanged, previously managed copy or
a recognized older official copy. A previous copy is backed up when replaced;
unknown or locally customized templates are preserved. The managed SHA-256 marker
is stored in Home Assistant `.storage/venta_homekit_native.template.json`.
LocalTuya must already be installed for synchronization to work.
A manual option remains: run `install_localtuya_template.py` to install a missing
template; a different existing template requires explicit `--replace`, with
backup. Existing LocalTuya device config entries, entity IDs and credentials
are never changed by template synchronization. No keys, cloud credentials or
device secrets are bundled.

The HomeKit humidifier type registry is globally redirected through a narrowly
scoped factory: the configured Venta entity uses the existing
`VentaEnhancedHumidifier` subclass, while **every other humidifier uses the
original Home Assistant `HumidifierDehumidifier` class**, without Venta linked
services. The bridge entry is resolved by title, no fixed ID. Repeated setup
is idempotent. Required native HomeKit/PyHAP methods are checked before registry
mutation; incompatible versions fail closed without patching the registry.

Main HumidifierDehumidifier target state: 0=Auto, 1=Humidify.
Fanv2 linked service: TargetFanState Auto=1, Manual=0.
Auto Switch linked service: On switches to Auto; Off switches an already
running automatic device to Manual without powering off the machine.
Linked Lightbulb: LED power/brightness.
Linked TemperatureSensor: HA sensor state.
The main humidity target is handled by HA's native HomeKit implementation.

The integration still relies on internal HomeKit and HAP-python APIs and
modifies the global `TYPES` registry; even with entity-scoped construction this
is **not a supported HA extension API**. CI runs the real Home Assistant/PyHAP
allocation algorithms on synthetic accessories to compare AID/IID identities
across simulated reload/restart cycles. This does **not** test existing Apple
Home pairings or a real running HomeKit server. No user pairings or `.storage`
files may be deleted or rewritten as part of an upgrade test.

## Model contracts (1.3.0 candidate)

The immutable [AW730 model profile](MODEL_PROFILES.md) records the original DP mapping and fan/LED conversions, verified against the unchanged bundled YAML by repository CI. It does not detect hardware or change existing bindings; no other model is enabled.

## UI configuration (released in 1.2.0)

The [entity-discovery plan](ENTITY_DISCOVERY.md) restricts helper choices to the same LocalTuya device and config entry. The UI wizard requires explicit confirmation of each role; Options stages changes and Reconfigure applies only reviewed same-bridge mappings for the next restart. The YAML path remains supported. See [release evidence](RELEASE_1_2_0.md) and [Options and Repairs](OPTIONS_AND_REPAIRS.md). The historical canary retained YAML; actual UI cutover was not performed.
