# Venta AW730 — compatibility and support

Status recorded: 2026-11-22. Only combinations backed by actual checks are marked **Verified**. Other Venta products and firmware variants are **not supported claims** until tested. Update this matrix after evidence from a real device and an isolated Home Assistant test environment.

## Compatibility matrix

| Layer | Tested combination / scope | Status and evidence |
|---|---|---|
| Physical air washer | **Venta AW730 AeroStyle Compact**, Smart Life / Tuya variant | **Verified** with one physical unit; on/off and readback, sensors and modes exercised on 2026-11-21/22 |
| Local protocol | Tuya LAN **3.4** | **Verified** for that unit through LocalTuya; other Tuya revisions untested |
| LocalTuya | [xZetsubou/hass-localtuya](https://github.com/xZetsubou/hass-localtuya), **2026.10.0** | **Verified** on H96; 18 imported LocalTuya entities using bundled `venta_aw730.yaml` |
| Home Assistant | Home Assistant **2026.11.1** (Container) | **Verified** for the installation checked on 2026-11-21/22; later stable/beta versions must pass their own regression checks |
| Venta extension | `venta_homekit_native` **1.0.4** (Marketplace custom repository) | **Verified** installed; manifest, managed template and source checked by SHA-256 |
| Apple Home | Existing HomeKit Bridge, Venta as **one** humidifier with linked fan, Auto, LED and temperature services | **Verified** for this bridge/accessory arrangement; not a guarantee for other iOS/HomeKit versions |
| Yandex / Alice | Yaha Cloud exports the **same** HA humidifier and Venta LED helpers | **Export membership verified** from Home Assistant configuration; voice-command behavior is **not independently verified** |
| Other AW7xx / other Venta models / firmware variants | No repeatable hardware test evidence yet | **Unverified / not claimed supported**; do not use the AW730 mapping without reviewing model-specific DP data |
| Native Venta v0/v2/v3 protocols, or direct Tuya LAN without LocalTuya | Not implemented here | **Unsupported by this repository** |

The device firmware version and any variations of its DP schema were not independently recorded. Do not infer universal compatibility from one tested device. Avoid submitting serial numbers, cloud Device IDs, keys or private addresses as evidence.

## Installation and non-destructive verification

1. Install the tested [LocalTuya fork](https://github.com/xZetsubou/hass-localtuya) and configure your **own** Smart Life / Tuya device through its configuration UI. Confirm this is the AW730 Tuya 3.4 variant before applying the supplied template.
2. Install Venta AW730 using the [custom Marketplace repository](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant) or the [README instructions](../README.md). Ensure LocalTuya has a `templates` directory.
3. Configure the Venta LocalTuya device with bundled `venta_aw730.yaml` and confirm the expected entities: humidifier, fan speed, temperature, humidity, PM2.5, water level and LED. Three service reset buttons are **not validated**: do **not** press them during verification.
4. Link Venta to an **existing** HomeKit bridge using `examples/configuration.yaml.example` and your own entity IDs. Do not create a duplicate accessory or unpair the old one. For Yaha Cloud, export the same humidifier entity only after confirming its HA state.
5. Before device-changing tests: make an HA configuration backup and record the initial power mode, target humidity and HomeKit pairing state. For a non-destructive check, read entity availability, mode and sensors and run Home Assistant configuration validation. Do not issue commands to the device without authorization.

## Updating and recovery

- Marketplace updates only the Venta integration files. On the next HA setup, `sync_managed_template` installs a missing LocalTuya template or updates an unchanged previously managed copy (or a recognized older official copy), backing up the previous template. **Customized templates are preserved.** A redirected LocalTuya templates directory or a symlinked `.storage` tracking marker is refused before writing. A previous managed template is retained as a timestamped `.bak`, which can be restored manually after checking it. Existing LocalTuya config entries, entities and local keys are never rewritten.
- If the template is absent, check that LocalTuya is installed first. For a **manual** template installation use `install_localtuya_template.py`; to replace a differing existing file requires `--replace` and creates a backup. Do not replace a customized template before reviewing its differences.
- If a device is unavailable, check the current HA/LocalTuya version, protocol version and entities and first resolve the underlying LAN/LocalTuya error. Don't delete the config entry, reset service counters, or re-pair HomeKit as a troubleshooting shortcut.
- If a new Venta/Home Assistant version breaks behavior, stop further changes, inspect redacted logs, compare the installed version to the last known good, and restore from a **verified** backup/previous supported package using the administrator's approved recovery procedure. Recheck HomeKit identity before declaring recovery. The repo does not yet provide an automated live rollback.
- HomeKit behavior uses internal Home Assistant/PyHAP APIs. Treat upgrades outside the tested combination as unverified until isolated CI and HomeKit compatibility tests pass.

## Safe diagnostic report (read-only)

The source version after 1.0.4 adds an opt-in `venta_homekit_native.log_diagnostics` service that reports only safe status categories. It is **not** present in the installed 1.0.4 baseline. See [diagnostic service guide](DIAGNOSTICS.md).

To file an issue use [Bug report](../.github/ISSUE_TEMPLATE/bug_report.yml). Include only:

- Model as printed on the unit (e.g. AW730), whether it is a Smart Life/Tuya device; firmware **version** if known, but never serial/Device ID.
- Venta integration version, Home Assistant version/install type, LocalTuya version, Tuya protocol version and which integration layer is affected.
- Steps starting from a known state; the expected result and the observed state (without a physical reset or repeated pairing).
- Whether the problem also happens in Home Assistant before Apple Home/Yandex; whether a restart, update or template sync preceded it.
- **Redacted** warning/error log lines and timestamps, only if relevant. Remove local keys, tokens, IP/MAC addresses, usernames, HomeKit pairing storage, network topology, automation secrets and account/device identifiers.

For suspected vulnerabilities, use [private security reporting](../SECURITY.md), not a public bug issue.
