# Releasing Venta AW730 — reproducible workflow

This is a maintainer procedure, not a user installation instruction. Canonical Marketplace source: [GitHub](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant); public mirror: [GitVerse](https://gitverse.ru/dmitriy_1ebedev/venta-aw730-homeassistant).

**Current baseline (2026-11-22):** installed component version 1.0.4; no GitHub Releases were published when this procedure was added. No new version, tag, asset or installed upgrade is implied by preparing this document. Home Assistant's existing bridge, pairing and LocalTuya entries must remain intact.

## Release preflight

1. Check `ROADMAP.md`, active MCPshka lease/jobs/deployment and clean local `main`. Capture the exact full local commit and its Git tree, current manifest version, and the last known-good installed component and backup. Do not force-push or edit earlier tags.
2. For a new version, update `custom_components/venta_homekit_native/manifest.json`, `CHANGELOG.md`, the version badge in both README files and release notes. Use one semantic version in all four locations.
3. Run `python -m compileall -q custom_components tests scripts`, `python -m unittest discover -s tests -v` and `python scripts/check_repository.py`. Run `python scripts/build_release.py --expected-tag vX.Y.Z --output /tmp/venta-aw730-vX.Y.Z-manual.zip`; capture its printed SHA-256. The script refuses overwrite and includes only the Venta component.
4. Review the tree for secrets and licenses. CI checks of patterns are a guardrail, not proof that all historical commits are free of secrets. Verify GitHub Actions Python, JS, HACS and hassfest checks on the **exact candidate tree**; confirm GitVerse CI independently via `git_provider_query ci_runs`. A green CI of an older mirror does not validate the current release.
5. Check `SECURITY.md` and `THIRD_PARTY_NOTICES.md`. Review HomeKit internal API changes and the LocalTuya managed-template behavior. Do not let a HACS `ignore: topics` exception be mistaken for catalog admission; see [CI audit](CI_SECURITY.md).

## Isolated installation and rollback gate

6. The offline archive test verifies that all files are under `custom_components/venta_homekit_native/`, the manifest is valid, and a **simulated** Home Assistant config with LocalTuya template directory accepts an initial template and idempotent re-run. This is **not** a real Home Assistant runtime or a HomeKit functional test.
7. Before publishing a runtime-changing release, install the exact candidate into a **disposable Home Assistant instance** with the supported version and a clean fake device configuration. Verify startup, dependency resolution, configuration validation, source version, and diagnostics. Run HomeKit/PyHAP behavior regression tests or record them as blocking; do not claim hardware behavior from a fake device.
8. Capture a reversible upgrade procedure: last-good source/tag/tree SHA-256, backup location and restore procedure. In production, a separate authorized canary requires a verified backup and a path back to the previous component. After rollback, verify HomeKit accessory identity, LocalTuya entities and system health before acceptance. Do not unpair Apple Home or reset the device to make a test pass.

## Tag, GitHub Release and Marketplace

9. **Only after successful preflight and authorized release:** create an immutable `vX.Y.Z` tag pointing to the reviewed commit. Confirm it did not exist, and verify its target SHA against the candidate. Do not retag or overwrite previous releases. Create GitHub Release notes with supported combinations, changes, known limits, migration effects, release SHA/tree and rollback instructions. Only attach a candidate ZIP if manual-install semantics are verified; HACS may prefer the source release format.
10. Check the release through the GitHub API (not just a browser badge). Confirm manifest/tag/notes match and Marketplace sees the intended version. A tag being present does **not** prove Home Assistant has installed it; distinguish published, installed and production accepted.
11. Mirror the **same reviewed tree** to GitVerse using an authorized route, without force. Compare source file tree hashes/bytes. If the GitVerse mirror cannot be updated, keep the release gate **HOLD** and document the blocker; do not silently claim both repositories are synchronized.
12. Update `ROADMAP.md`, `CHANGELOG.md` and the acceptance checkpoint with commit SHA, CI IDs, release URL/tag, archive SHA-256, isolated installation evidence, rollback evidence and Marketplace result. Close P01.2 only when its actual Exit criteria are met.

## Safety and separation of responsibilities

- `build_release.py` creates a reproducible component-only archive; it does not use device credentials, invoke Home Assistant, publish tags, push Git or deploy.
- If any release tool is unavailable, do not manufacture a successful release state from passing unit tests. Record exactly which acceptance gate is unfulfilled.
- The integration can rely on internal Home Assistant HomeKit/PyHAP APIs; tests against the next HA release are required before expanding claimed support.
- Releasing `1.0.5` means more than changing `manifest.json`: it must pass the **tag → archive → isolated install → CI → publication → acceptance** chain.
