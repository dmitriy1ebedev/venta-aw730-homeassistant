# Architecture

Venta AW730 --(Tuya LAN 3.4 / LocalTuya)--> Home Assistant humidifier
        -> venta_homekit_native -> existing HomeKit Bridge -> Apple Home / Siri

Optional: HA humidifier -> Yaha Cloud -> Yandex Smart Home / Alice

Marketplace manages only `custom_components/venta_homekit_native/`, not LocalTuya.
This integration ships `templates/venta_aw730.yaml` inside its own folder.
`install_localtuya_template.py` copies that file into LocalTuya's templates
folder only on explicit invocation, with idempotency and backup on --replace.
No keys, cloud credentials or device secrets are bundled. The template remains
updated with new Marketplace releases; run the installer again to synchronize
a previously installed LocalTuya template, if needed.

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
