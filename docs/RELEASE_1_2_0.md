# Venta 1.2.0 — protected production release and rollback

**State: H96 operational canary installed 2026-11-23; formal protected
release pending.** The owner explicitly authorized a Remote Desktop Commander
canary. Its private transaction receipt reads `VERIFIED`, the container runs
Venta 1.2.0 and Home Assistant is healthy. This manual installation is NOT
a protected-main merge, immutable tag, GitHub Release, Face ID recipe pin or
`project_release_status=INSTALLED`. Those are distinct outstanding gates.

## Why the production install is conservative

The existing Venta 1.0.4 is a working YAML-managed extension of the
**original** HomeKit bridge. Venta 1.2.0 adds an optional UI wizard and
entity binding review but **does not migrate or remove the old YAML block
during the package update**. Legacy configuration remains authoritative.
No new HomeKit server, pairing reset, LocalTuya config edit, physical
device command, or Apple Home re-pair is permitted by the release script.

The deployed integration version is declared in
`custom_components/venta_homekit_native/manifest.json`, the Changelog
and `VERSION`. The release zip is deterministic and must carry only
the public integration. Existing custom templates and any original
component files are preserved in an on-host private rollback directory.

## The owner-approved release recipe

`.mcpshka/release.json` pins the exact commands:

1. **Preflight:** Verify the installed version is 1.0.4, the new source is
   1.2.0, the running Home Assistant container is healthy, there is
   exactly one applicable original HomeKit bridge, the legacy YAML
   mapping remains present, and a fresh (under two hours old) **native
   Home Assistant backup** can be restored byte-for-byte into private
   RAM-backed scratch. All six critical files must match the current
   machine. If anything differs, stop before touching production.
2. **Stage:** Make root-only copies of the original component plus
   YAML, HA config entries and HomeKit AID/IID/pairing files under
   `/var/lib/venta-aw730-releases/1.2.0` (0700 directory / 0600
   files). Prepare the new public component in a non-installed sibling
   directory on the same filesystem. No live files are changed yet.
3. **Install:** Atomically move the old component to a sibling backup
   and move the candidate into place. The old files are **never
   deleted**. The receipt records a precise `INSTALLED_NEEDS_RESTART`
   state.
4. **Restart:** One controlled `docker restart homeassistant` through
   the owner-approved release recipe.
5. **Verify:** The Home Assistant container returns to healthy. YAML,
   HomeKit AID/IID maps, existing bridge and LocalTuya/Yaha config-entry
   identities, all pairing keys/paired clients and accessories hash must
   remain unchanged. HA may legitimately rewrite unrelated integrations'
   config-entry metadata after boot; HomeKit may increment its integer
   `config_version` while keeping all other `.state` fields identical.
   Reject any changed protected entry, removed pairing, changed AID/IID,
   modified accessory hash or decreasing HAP configuration revision.
   The installed component's manifest must read 1.2.0. No YAML-to-UI
   migration occurs automatically.

Any install/restart/verification failure triggers the recipe's **own
rollback**: pre-validate the private snapshots, stop HA if the live
component was changed, put back the original component and protected
pairing snapshot, start HA and wait for healthy. If HA has already made
unrelated config-entry updates or raised HomeKit's harmless config revision,
preserve those newer fields when the original protected identities match.
A pre-install error
does **not** stop HA or rewrite its storage. A corrupt rollback snapshot
is rejected *before* stopping HA. The previous component and failed
candidate stay available for diagnosis.

Only `project_release_status=INSTALLED` confirms the formal protected
release; the separate owner-authorized H96 canary has a private verified
transaction receipt. Independently compare
original Venta, other HomeKit accessories and Yandex Cloud exports.
If any real-world Apple Home or LocalTuya behavior is wrong despite
health checks, treat production acceptance as failed and perform
the separately approved rollback. No user credentials or pairing
material are logged or uploaded.

## Checks still required

- Protected source merge and exact-release GitHub/GitVerse CI.
- Immutable tag and GitHub Release of the exact approved 1.2.0 commit.
- Face ID pin of the formal release recipe; actual H96 canary already
  passed a controlled HA restart and preserved both original HomeKit bridge
  identities, pairing material and the LocalTuya/Yaha exposed humidifier.
  Direct Apple Home app functionality still needs independent acceptance.
- Optional YAML→UI cutover only after separate explicit acceptance:
  verify the existing bridge exact entry ID, backup, stage proposal,
  remove YAML *after* safe migration, restart and verify no duplicate
  HomeKit accessory. Any issue: restore prior snapshot.

**Never** modify the live HA directory from an unreviewed dirty checkout,
overwrite native backups, disclose HomeKit pairing data, or treat a manual
canary as an approved protected release. Maintain the private prior-version
snapshot until Apple Home functionality and release provenance are accepted.
