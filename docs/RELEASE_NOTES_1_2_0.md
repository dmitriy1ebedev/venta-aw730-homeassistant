# Venta AW730 1.2.0

This release introduces an **optional** Home Assistant UI configuration flow for existing Venta AW730 installations, guarded LocalTuya device/entity binding review, and non-applying Options, Reconfigure and Repairs previews.

## Compatibility and safeguards

- Confirmed scope: Venta **AW730** with the tested LocalTuya/Tuya LAN 3.4 combination and Home Assistant 2026.11.1/2026.11.2. Other AW7xx variants have **not** been established as supported.
- Existing seven-key YAML installations remain authoritative after package updates. **No automatic YAML-to-UI migration, LocalTuya reconfiguration, HomeKit bridge replacement, or Apple Home re-pairing** is performed.
- HomeKit AID/IID identity, unrelated HomeKit accessories and rollback behavior were exercised in disposable Home Assistant runs and fixture tests.
- The owner separately verified an operational canary on H96 with HA healthy and the original paired HomeKit bridge. This does **not** imply all optional UI migration paths were exercised against the physical AW730.

## Installation and rollback

Install from the exact GitHub version tag with your Home Assistant custom repository / HACS workflow, or use the attached component-only manual-install ZIP. **Back up Home Assistant and the original custom component before upgrading.** Do not replace or delete existing HomeKit pairing records, LocalTuya credentials, device entries or custom templates. To roll back, restore the previous component together with its approved private backup and verify the unchanged HomeKit identity and original LocalTuya entities before resuming operation.

The release attachments include the deterministic component ZIP and source/asset SHA-256 provenance. The GitVerse mirror is tracked independently; a lagging mirror is not equivalent to this GitHub release.

## Release verification

The tag is created once from a validated commit on protected GitHub `main`, after all five required CI jobs succeed. The publisher rejects unexpected versions, mismatched source heads, re-targeting a published tag, and unsafe release archives. It checks Home Assistant on a disposable fixture, downloads the published ZIP and verifies its SHA-256 before accepting the run.

See [release procedure](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/blob/main/docs/RELEASING.md) and [CI security limitations](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/blob/main/docs/CI_SECURITY.md).
