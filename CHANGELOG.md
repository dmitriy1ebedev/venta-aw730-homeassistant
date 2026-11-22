# Changelog

## 1.0.5 (2026-11-22)
- Maintenance release candidate based on the reviewed 1.0.4 implementation: no changes to Tuya DP mappings, HomeKit accessory behavior, pairing identifiers or existing LocalTuya configuration entries.
- Establish version-consistent, reproducible component-only release packaging, isolated Home Assistant validation and an explicit rollback procedure. Work planned for 1.1.0 stays outside this maintenance branch.

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
