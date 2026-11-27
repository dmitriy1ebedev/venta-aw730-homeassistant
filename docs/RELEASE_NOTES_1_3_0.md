# Venta AW730 1.3.0

## Changes

- Optional read-only water-level and maintenance notifications with startup/unavailable guards and no automatic counter reset.
- Explicit AW730/Tuya LAN 3.4 model profile; unknown models and protocols are unsupported.
- Hardened Apple Home fan, Auto and LED commands, with preservation of existing HomeKit identity and single-device control through LocalTuya/Yaha.
- Optional local Lovelace card and history in the source repository (manual dashboard installation; not part of the component-only ZIP).
- Improved RU/EN documentation, diagnostics and compatibility coverage.

## Compatibility and limits

AW730 is the only supported model. Home Assistant 2026.11.1, 2026.11.2, 2026.11.3 and 2026.12.0b0 were covered by isolated engineering checks with LocalTuya 2026.10.0. This release is not a claim of a physical-device upgrade, Apple Home/Alice client acceptance or maintenance reset validation. These checks remain in [#43](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/issues/43); additional model support remains in [#41](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/issues/41). LocalTuya is retained.

No automatic YAML-to-UI migration, re-pairing, credential changes or device reconfiguration. Back up the existing component and Home Assistant configuration before installation. For rollback, restore the previous 1.2.0 component and approved private backup, verify HA health and the unchanged paired HomeKit bridge. Do not delete the existing device or pairing.

## Verification

The GitHub publisher requires the successful seven-job validation run for the exact current main commit, builds a deterministic component-only ZIP, verifies an isolated Home Assistant installation, creates an immutable tag, and re-downloads the published ZIP to verify SHA-256. GitVerse mirrors the reviewed public source. No production installation is performed by this publication.
