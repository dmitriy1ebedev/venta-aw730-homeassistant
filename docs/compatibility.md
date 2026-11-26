# Venta AW730 — compatibility and support

Status recorded: 2026-11-26. Only combinations backed by actual checks are marked **Verified**. Other Venta products and firmware variants are **not supported claims** until tested. Update this matrix after evidence from a real device and an isolated Home Assistant test environment.

## Compatibility matrix

| Layer | Tested combination / scope | Status and evidence |
|---|---|---|
| Physical air washer | **Venta AW730 AeroStyle Compact**, Smart Life / Tuya variant | **Verified** with one physical unit; on/off and readback, sensors and modes exercised on 2026-11-21/22 |
| Local protocol | Tuya LAN **3.4** | **Verified** for that unit through LocalTuya; other Tuya revisions untested |
| LocalTuya | [xZetsubou/hass-localtuya](https://github.com/xZetsubou/hass-localtuya), **2026.10.0** | **Verified** on H96; 18 imported LocalTuya entities using bundled `venta_aw730.yaml` |
| Home Assistant | **2026.11.1** on H96; **2026.11.2**, **2026.11.3**, and **2026.12.0b0** isolated CI | **2026.11.1 verified in production**; **2026.11.2 tested only in disposable CI** (HomeKit API, YAML restore, synthetic UI setup). The 2026.11.3 stable and 2026.12.0b0 beta passed disposable CI only (synthetic LocalTuya registry; no live device) |
| Venta extension | `venta_homekit_native` **1.2.0** (custom Marketplace repository / GitHub Release) | **Verified operational canary on H96** with HA healthy and original HomeKit bridge identity, accepted 2026-11-23; previous **1.0.4** retained as rollback baseline |
| Apple Home | Existing HomeKit Bridge, Venta as **one** humidifier with linked fan, Auto, LED and temperature services | **Verified** for this bridge/accessory arrangement; not a guarantee for other iOS/HomeKit versions |
| Yandex / Alice | Yaha Cloud exports the **same** HA humidifier and Venta LED helpers | **Export membership verified** from Home Assistant configuration; voice-command behavior is **not independently verified** |
| Other AW7xx / other Venta models / firmware variants | No repeatable hardware test evidence yet | **Unverified / not claimed supported**; do not use the AW730 mapping without reviewing model-specific DP data |
| Native Venta v0/v2/v3 protocols, or direct Tuya LAN without LocalTuya | Not implemented here | **Unsupported by this repository** |

## Home Assistant release-channel evidence (V110-05)

| Home Assistant release | Test level | Verdict / next safe action |
|---|---|---|
| **2026.11.1** (stable patch) | **Tested on H96** with Venta 1.2.0 canary; separate disposable GitHub CI | **TESTED**, existing HomeKit identity and LocalTuya/Yaha configuration preserved; no new device writes |
| **2026.11.2** (stable patch, latest published when checked 2026-11-23) | **Disposable CI only**, including real HA/PyHAP API imports, synthetic ConfigFlow, registry, three boots and YAML rollback (GitHub Actions 45137841054, 5/5 PASS) | **TESTED IN ISOLATION**; does not authorize production HA upgrade or establish physical-device compatibility |
| **2026.11.3** (stable, published 2026-11-23) | Real HA/PyHAP, synthetic LocalTuya registry, ConfigFlow, identity, isolated boots and rollback | **TESTED IN ISOLATION**; GitHub Actions 45759800364, 7/7 PASS |
| **2026.12.0b0** (beta, published 2026-11-25) | Same isolated checks using upstream generic x86-64 image | **TESTED IN ISOLATION**; GitHub Actions 45759800364, 7/7 PASS; never install beta on H96 for this check |
| Other untested HA versions / HomeKit or LocalTuya API changes | No isolated evidence on these exact versions | **UNVERIFIED**, fail closed for new installs/releases until compatibility smoke passes; never modify the working existing bridge as a test shortcut |

Evidence for 2026.11.3 and 2026.12.0b0: GitHub PR #28, source `7c03516ebd37a9d03ed567429739faa683d8cfbd`, [run 45759800364](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/runs/45759800364). Initial LocalTuya coverage is a synthetic registry/configuration contract. Follow-up GitHub Actions [45760621426](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/runs/45760621426), source `286cd3f4cdcc26778c17e894a9fa5e6f8ffeee1d`, also imported pinned upstream LocalTuya 2026.10.0 (commit `7f3be1999f581863ffa984e86ed359857f8bcab1`) and checked platform APIs and synthetic DP selectors on stable and beta. This is not a live LocalTuya device connection or physical-device test.

The GitHub CI source SHA, Home Assistant container version and result must be recorded together; a prior success is not transferable to a new beta image. CI's network-disabled disposable tests do not issue commands to the physical air washer or access private HomeKit pairing records. Upstream beta schedule and versioning: https://contributors.home-assistant.io/releases/how-it-works/ .

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
- If a new Venta/Home Assistant version breaks behavior, stop further changes, inspect redacted logs, compare the installed version to the last known good, and restore from a **verified** backup/previous supported package using the administrator's approved recovery procedure. Recheck HomeKit identity before declaring recovery. The guarded 1.2.0 release recipe includes an explicit rollback, but the formal protected adoption is not yet approved, and ordinary Marketplace upgrades have no general automatic rollback.
- HomeKit behavior uses internal Home Assistant/PyHAP APIs. Treat upgrades outside the tested combination as unverified until isolated CI and HomeKit compatibility tests pass.

## Safe diagnostic report (read-only)

The installed Venta **1.2.0** includes an opt-in `venta_homekit_native.log_diagnostics` service returning only privacy-safe status categories. The archived **1.0.4** rollback baseline does not include this service. See [diagnostic service guide](DIAGNOSTICS.md).

To file an issue use [Bug report](../.github/ISSUE_TEMPLATE/bug_report.yml). Include only:

- Model as printed on the unit (e.g. AW730), whether it is a Smart Life/Tuya device; firmware **version** if known, but never serial/Device ID.
- Venta integration version, Home Assistant version/install type, LocalTuya version, Tuya protocol version and which integration layer is affected.
- Steps starting from a known state; the expected result and the observed state (without a physical reset or repeated pairing).
- Whether the problem also happens in Home Assistant before Apple Home/Yandex; whether a restart, update or template sync preceded it.
- **Redacted** warning/error log lines and timestamps, only if relevant. Remove local keys, tokens, IP/MAC addresses, usernames, HomeKit pairing storage, network topology, automation secrets and account/device identifiers.

For suspected vulnerabilities, use [private security reporting](../SECURITY.md), not a public bug issue.
