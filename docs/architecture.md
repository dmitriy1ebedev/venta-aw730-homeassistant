# Architecture

Venta AW730 --(Tuya LAN 3.4 / LocalTuya)--> Home Assistant humidifier
        -> venta_homekit_native -> existing HomeKit Bridge -> Apple Home / Siri

Optional: HA humidifier -> Yaha Cloud -> Yandex Smart Home / Alice

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

The existing HomeKit humidifier accessory is patched only if its entity
matches configuration.yaml. Bridge entry is resolved by title, no fixed ID.

Main HumidifierDehumidifier target state: 0=Auto, 1=Humidify.
Fanv2 linked service: TargetFanState Auto=1, Manual=0.
Auto Switch linked service: On switches to Auto; Off switches an already
running automatic device to Manual without powering off the machine.
Linked Lightbulb: LED power/brightness.
Linked TemperatureSensor: HA sensor state.
The main humidity target is handled by HA's native HomeKit implementation.

The integration relies on internal HomeKit and HAP-python APIs and uses a
global HomeKit TYPES patch. Treat as an experiment, not a supported HA API.
Do not install on a production system without first testing a backup.
