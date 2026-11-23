# Venta 1.2.0 — protected production release and rollback

**State as of 2026-11-23:** Owner-approved H96 operational canary runs
Venta **1.2.0**, Home Assistant is healthy and the private canary receipt is
`VERIFIED`. GitHub PR #19 was merged; an immutable GitHub Release
[`v1.2.0`](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/releases/tag/v1.2.0)
and its checksum-verified source archive were published. The public GitVerse
mirror has independently passed CI on the same current source tree.
**Formal MCPshka production release is not complete:**
`project_release_status=NOT_STARTED` and the protected recipe is not Face ID
pinned. These states must not be conflated. This canary did not perform the
optional YAML-to-UI cutover or prove interactive Apple Home app operation.

## Why the production install is conservative

Before the approved canary, Venta 1.0.4 was the working YAML-managed
extension of the **original** HomeKit bridge. Venta 1.2.0 adds an optional UI wizard and
entity binding review but **does not migrate or remove the old YAML block
during the package update**. Legacy configuration remains authoritative.
No new HomeKit server, pairing reset, LocalTuya config edit, physical
device command, or Apple Home re-pair is permitted by the release script.

The deployed integration version is declared in
`custom_components/venta_homekit_native/manifest.json`, the Changelog
and `VERSION`. The release zip is deterministic and must carry only
the public integration. Existing custom templates and any original
component files are preserved in an on-host private rollback directory.

## Formal release recipe (not yet Face ID-pinned)

`.mcpshka/release.json` declares the historical 1.0.4 → 1.2.0 release
procedure; it is **not** an approval or authorization to run again. Its
preflight requires an installed 1.0.4 component, but H96 already runs 1.2.0.
**Do not replay this version-specific install/restart** over the healthy canary.
Formal adoption needs a newly reviewed, idempotent verify-only/adoption plan
and the owner's separate Face ID approval; no restart is justified merely to
change bookkeeping.

The historical recipe includes:

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

## Verified publication and remaining gates

- **DONE — public release:** GitHub PR #19 merged; tag `v1.2.0` points to
  immutable commit `49d0c64e`. Published ZIP SHA-256 starts `1d46a997`;
  postpublication isolated HA smoke CI `45132027560` passed.
- **DONE — current public source:** GitHub main CI `45140789084` passed 5/5;
  GitVerse `validate.yml` run `2191055` succeeded on the identical source
  tree, using safe fast-forward public mirroring without force-push.
- **DONE — H96 operational canary:** Controlled restart, saved rollback to
  1.0.4 and preservation of both original HomeKit bridge identities and the
  LocalTuya/Yaha humidifier were verified. The owner accepted unchanged
  behavior; no second restart or pairing change was necessary.
- **PENDING — protected release record:** `project_release_status=NOT_STARTED`;
  the existing 1.0.4-only preflight cannot be repeated against installed 1.2.0.
  A separately approved adoption/verification procedure is required.
- **PENDING — direct Apple Home UI acceptance:** A healthy container and
  synthetic HomeKit tests are not a substitute for real interactive operation.
- **DEFERRED — optional YAML→UI cutover:** Only after separate owner approval,
  verify the exact existing bridge ID, backup, stage proposal, remove YAML
  *after* safe migration, restart, and confirm no duplicate HomeKit accessory.
  If anything differs, restore the previously verified snapshot.

**Never** modify the live HA directory from an unreviewed dirty checkout,
overwrite native backups, disclose HomeKit pairing data, or treat a manual
canary as an approved protected release. Maintain the private prior-version
snapshot until Apple Home functionality and release provenance are accepted.
