# Venta 1.2.0 — migration from seven-key YAML (V120-03)

**Experimental, not released or installed.** This is an interactive,
two-start transition. The integration must continue to use the **same**
LocalTuya humidifier entity, the **same** HomeKit bridge entry ID and the
same five associated entities. Do not reset Apple Home pairing, create another
HomeKit bridge or edit Home Assistant `.storage` manually.

## Before entering the wizard

1. Verify the currently installed YAML-based Venta works, including its
   existing bridge in Apple Home. Export and **test** an HA configuration backup
   which includes `configuration.yaml` and `.storage`. Do not expose the
   contents publicly. A successful archive listing alone is not a restore test.
2. Confirm seven YAML keys exist in `venta_homekit_native`:
   `humidifier_entity`, `bridge_title`, `fan_entity`, `led_entity`,
   `brightness_entity`, `temperature_entity`, `humidity_entity`.
3. Use **Settings → Devices & services → Add integration → Venta**.
   When an active YAML installation exists, the wizard offers
   `migrate_yaml`, not another installation. It pins the actual HomeKit
   `entry_id`, verifies the LocalTuya entity registry and asks for explicit
   backup and restart acknowledgements. Any unclassified temperature/humidity
   sensor requires an additional manual confirmation.

## Applying the transition

4. Submit the migration only if the linked entity IDs and bridge are correct.
   This creates **one** Venta config entry. **The running YAML controller is
   not unloaded or modified.** Home Assistant may temporarily show a setup
   error for the new entry while the YAML owner still runs; this is intentional
   fail-closed behavior. Do **not** attempt to re-pair HomeKit.
5. Remove **only** the entire `venta_homekit_native:` block containing the
   seven keys from `configuration.yaml`. Leave the existing `homekit:`,
   LocalTuya, device registry, bridge and pairing storage untouched.
   Run HA's configuration validation before an approved restart.
6. Restart HA once and check the new config entry; the same pinned HomeKit
   bridge and humidifier entity must be reused. Verify AID/IID/paired identity
   and other HomeKit accessories. Do not accept if duplicated accessories or
   errors occur.

## Rollback

If validation fails **before restart**, restore the original seven YAML keys
from backup and do not restart. The YAML controller continues to own Venta.
If restart has occurred, restore the original YAML block and perform an
approved HA restart; the new config entry fails closed while YAML is present.
**Do not delete the new config entry, reset HomeKit, re-pair, or hand-edit
`.storage` as part of automatic rollback.** Entry cleanup and safe unload
belong to V120-04 and require separate acceptance.

Automatic `SOURCE_IMPORT` intentionally aborts rather than importing YAML
unattended. Entry creation requires the owner's explicit confirmation;
all operations are inert until the installation and restart gates.
The disposable smoke tests use synthetic LocalTuya registries and never
send physical commands.

## Acceptance not yet satisfied

V120-03 needs idempotent migration tested with a genuine disposable Home
Assistant restart, AID/IID consistency, a **restored** synthetic HA snapshot,
and an approved production canary with verified rollback readiness.
Green Python tests and isolated ConfigFlow smoke are necessary but not
sufficient. V120-01 and MCP-267 remain separate blockers.
