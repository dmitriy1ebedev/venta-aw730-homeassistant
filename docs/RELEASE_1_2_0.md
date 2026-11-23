# Venta 1.2.0 — protected production release and rollback

**State: candidate only.** The owner must approve the exact
`.mcpshka/release.json` by Face ID and the source must be merged to a
clean protected `main`. These conditions are enforced by MCPshka
`project_release`; a passing PR, sealed test or source archive is not an
installed release.

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
5. **Verify:** The Home Assistant container returns to healthy and its
   YAML, config-entry storage, AID/IID maps and HomeKit pairing state
   still match their pre-upgrade bytes. The only expected changed file
   is the Venta integration manifest, now 1.2.0. No UI migration occurs
   automatically.

Any install/restart/verification failure triggers the recipe's **own
rollback**: pre-validate the private snapshots, stop HA if the live
component was changed, put back the entire original component and all
six selected files, start HA and wait for healthy. A pre-install error
does **not** stop HA or rewrite its storage. A corrupt rollback snapshot
is rejected *before* stopping HA. The previous component and failed
candidate stay available for diagnosis.

The release manager is the only authority to report `INSTALLED`.
Immediately afterward, use MCPshka read-only HA checks and compare
original Venta, other HomeKit accessories and Yandex Cloud exports.
If any real-world Apple Home or LocalTuya behavior is wrong despite
health checks, treat production acceptance as failed and perform
the separately approved rollback. No user credentials or pairing
material are logged or uploaded.

## Checks still required

- Protected source merge and exact-release GitHub/GitVerse CI.
- Immutable tag and GitHub Release of the exact approved 1.2.0 commit.
- Face ID pin of the release recipe, supervised production restart
  and verification of the real Venta/other original HomeKit accessories.
- Optional YAML→UI cutover only after separate explicit acceptance:
  verify the existing bridge exact entry ID, backup, stage proposal,
  remove YAML *after* safe migration, restart and verify no duplicate
  HomeKit accessory. Any issue: restore prior snapshot.

**Never** run this script from an unapproved dirty checkout or copy a
candidate manually into the live HA directory to bypass MCPshka.
