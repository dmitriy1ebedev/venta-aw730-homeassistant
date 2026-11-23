# Changelog

## 1.2.0 (2026-11-23)
- Introduce guarded Home Assistant config_flow, device-bound entity registry discovery and staged YAML→UI migration with preserved existing HomeKit bridge identity.
- Add non-applying Options review, explicit backup/restart-bound Reconfigure and fail-closed Repairs for missing original bindings.
- Preserve existing seven-key YAML installations without automatic migration, re-pairing or HomeKit bridge reload.
- Validate HomeKit/PyHAP identity in HA 2026.11.1/2026.11.2, six independent real HA cold starts, YAML rollback and private backup restoration.
- Keep sensitive HA snapshots, HomeKit pairing material and LocalTuya keys on the owner's host; never distribute them in CI or release packages.

## Unreleased
- Prepare a read-only, device-scoped entity-registry discovery helper for the future Venta 1.2.0 config flow. Require explicit user confirmation; never bind fan/LED from a different LocalTuya device or automatically migrate existing YAML/Apple Home.
- Route only the configured Venta entity to the enhanced HomeKit class; all other humidifiers retain the native HA class. Fail closed on missing HomeKit/PyHAP API contracts. Add isolated HomeKit AID/IID stability regressions (no pairing or live device).
- Add an explicit, read-only `venta_homekit_native.log_diagnostics` service returning a sanitized JSON response in Developer Tools (and optionally logging at INFO) with allow-listed versions, entity availability, HomeKit Bridge state and safe follow-up codes; excludes secrets, identifiers, raw sensor data and network information.
- Keep LocalTuya protocol error attribution separate from Home Assistant entity state; the service cannot infer handshake root causes.

## 1.0.4 (2026-11-22)
- Automatically reconcile managed LocalTuya templates when Venta starts after a Marketplace update; preserve customized templates and back up a prior managed version before replacement.
- Track managed template SHA-256 in Home Assistant `.storage`; do not rewrite already configured LocalTuya devices, their entity IDs or credentials.
- Align GitHub/GitVerse CI jobs with the capabilities of their runners: Python checks on both, HACS and hassfest on compatible GitHub runners.

## 1.0.3 (2026-11-22)
- Introduce original Venta vector branding and a wider, redesigned bilingual README presentation.
- No change to device DP mappings or existing HomeKit accessory identity.

## 1.0.2 (2026-11-22)
- Add validated Home Assistant YAML configuration schema and document the `reload_venta` service for hassfest.
- No change to HomeKit accessory identity or LocalTuya device mappings.

## 1.0.1 (2026-11-22)
- Repository maintenance: security and contribution policies, issue/PR templates, CODEOWNERS, CI and Marketplace validation checks; no device behavior change.
- Marketplace name changed to Venta AW730; new app icon and high-resolution icon.
- Bundled LocalTuya device template; safer installer with backup on replacement.
- Canonical duration (d) and PM2.5 (μg/m³) units, corrected water-level metadata.
- Simplified two-part installation instructions, retained existing HomeKit pairings.

## 1.0.0 (2026-11-22)
- Portable YAML parameterized HomeKit extension copied from tested Venta AW730 implementation.
- Apple Home Auto/Humidify/Off support; linked fan, LED, temperature and optional Auto control.
- Security notes, agent instructions and release checklist.
