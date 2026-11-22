# Venta AW730 v1.0.5 — maintenance release candidate

**Status: CANDIDATE, NOT RELEASED.** The canonical GitHub `main` contains unreleased 1.1.0 features and remains a separate line. This document describes only the `release/1.0.5` branch created from reviewed commit `7a47f34eb8665c6f138f66dc95461731e6530ab1`.

## Scope

- Version: `1.0.5` in the integration manifest, both README badges and CHANGELOG.
- No changes to existing Venta HomeKit accessory constructors, unique identifiers, Tuya LAN DP mappings or LocalTuya template logic versus the reviewed 1.0.4 source.
- Release engineering only: deterministic component-only ZIP, offline packaging checks, separate disposable Home Assistant 2026.11.1 / 2026.11.2 configuration and HomeKit command smokes, and a temporary downloadable CI candidate archive.
- The privacy-safe `log_diagnostics` service and scoped HomeKit accessory factory planned for `1.1.0` are **not** included here.

## Candidate archive fingerprint

The component-only ZIP contains 8 files and has SHA-256 `ba758a504584633ff73a3271b48c24424295bc6f26a40c52f711fb4ae4fc87c4`, independently reproduced by RDC on H96 and GitHub Actions [#45039389205](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/runs/45039389205) (5/5 PASS). Subsequent tests outside the component should not change the archive fingerprint.

`tests/test_maintenance_rollback.py` exercises synthetic 1.0.4 → 1.0.5 file replacement and restore of a backed-up component while checking that fake HA config-entry, entity and HomeKit markers stay unchanged. It is **not** a real paired bridge restart or production rollback.

## Preflight and isolated install

Run `python3 scripts/build_release.py --expected-tag v1.0.5 --output /tmp/venta-aw730-v1.0.5-manual.zip` on the exact candidate source. Record printed SHA-256 and check that the archive contains only `custom_components/venta_homekit_native/`, no secret files or symlinks. Do not replace existing archives.

CI stages this ZIP in a synthetic HA config, runs actual `homeassistant --script check_config` and calls installed native HA HomeKit APIs in **network-disabled** containers. These checks do **not** start HomeKit pairing or prove a real device connection.

The CI run may attach `venta-1.0.5-manual-candidate` as a short-retention artifact. An artifact is **not** a GitHub Release, a signed tag, an installed update or acceptance by the Marketplace catalog.

## Rollback and release gates

Before any installation, independently archive the original installed `custom_components/venta_homekit_native` directory and applicable HA configuration, ensure the archive is restorable, record source SHA-256 and verify device availability and existing HomeKit pairing ID. Restore only the Venta integration files if a canary fails, restart HA through the normal controlled workflow and check that the same entities, bridge and accessory identity return. Never reset Tuya/LocalTuya credentials or delete HA `.storage` or Apple pairing data as a workaround.

For actual publication, the maintainer must verify CI PASS, exact version/tag and archive SHA-256, immutable tag, release description, separate GitVerse mirror status, an isolated upgrade/rollback and an approved release action. **Do not publish or install while any applicable gate is unmet.** There are no implied production changes in this candidate branch.

Known limitations: HomeKit relies on private HA/PyHAP internals; no real paired HomeKit restart is exercised by synthetic CI. HACS `ignore: topics` remains a documented catalog-admission exception. The source remains restricted to tested Venta AW730, LocalTuya/Tuya LAN 3.4.
