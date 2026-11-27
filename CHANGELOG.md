# Changelog

## 1.3.0 (2026-11-27)
- Add optional read-only service advisories for AW730 water level and filter, cleaning and service intervals; guard startup/unavailable transitions and require repeated relevant events. Never reset a maintenance counter automatically.
- Add an optional local Lovelace dashboard and history for humidity, PM2.5, temperature, fan and water level (separate manual dashboard assets).
- Define an explicit AW730 Tuya LAN 3.4 model profile and validate the existing template digest and DP contract; reject unsupported models and protocols.
- Harden HomeKit fan and LED command validation, reject unavailable or malformed requests, and prioritize explicit Auto over simultaneous positive manual speed; preserve HomeKit identities and LocalTuya/Yaha bindings.
- Extend RU/EN support documentation and isolated real Home Assistant/PyHAP, browser, recorder and compatibility tests (2026.11.1, 2026.11.2, 2026.11.3 and 2026.12.0b0).
- Retain LocalTuya. Additional hardware models and live service-counter/platform command acceptance remain tracked in issues #41/#43.

## 1.2.0 (2026-11-23)
- Introduce guarded Home Assistant config_flow, device-bound entity registry discovery and staged YAML→UI migration with preserved existing HomeKit bridge identity.
- Add non-applying Options review, explicit backup/restart-bound Reconfigure and fail-closed Repairs for missing original bindings.
- Preserve existing seven-key YAML installations without automatic migration, re-pairing or HomeKit bridge reload.
- Validate HomeKit/PyHAP identity in HA 2026.11.1/2026.11.2, six independent real HA cold starts, YAML rollback and private backup restoration.
- Route only the configured Venta entity to the enhanced HomeKit class; preserve native classes for other humidifiers and fail closed on incompatible HomeKit/PyHAP APIs.
- Provide the read-only `venta_homekit_native.log_diagnostics` service with sanitized version, entity availability and bridge status; do not infer protocol handshake failures from entity states.
- Keep sensitive HA snapshots, HomeKit pairing material and LocalTuya keys on the owner's host; never distribute them in CI or release packages.

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
