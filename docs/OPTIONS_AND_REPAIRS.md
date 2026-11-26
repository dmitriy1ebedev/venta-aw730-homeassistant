# Venta 1.2.0 — Options, Reconfigure and Repairs (V120-04)

**Released in 1.2.0; the operational canary retained its existing YAML.** The UI workflows were exercised in isolation. A live transition or change of existing HomeKit pairing is not established by those tests; see [release evidence](RELEASE_1_2_0.md).

## Options: inspect and stage only

For a UI-managed Venta entry, choose **Options** to inspect the exact
existing HomeKit bridge and five related LocalTuya entities. The entry uses
the saved humidifier and does not permit selecting a different physical
device. Candidates are read from the current HA entity registry and must
belong to the same LocalTuya device and config entry; disabled, hidden or
misclassified entities are refused. Unknown temperature/humidity sensor
classes require separate, explicit confirmation.

Selecting a bridge and five roles, then checking the confirmation box,
creates **only an inert proposal in config entry options**. It does not
change the active HomeKit accessory, send a LocalTuya command, invoke
`reload_venta`, reload Home Assistant or change the pairing. Selecting
another valid bridge may be reviewed but **cannot be applied** through
the guarded reconfigure path: the Apple Home identity could change.
Invalid and foreign-device selections never save a proposal.

A saved proposal carries a snapshot of the entry's current mapping.
If the entry or registry changes before reconfigure, the proposal is
rejected and must be reviewed again.

## Reconfigure: approved same-bridge changes

For a reviewed proposal, launch Home Assistant's **Reconfigure** action.
Only the same `humidifier_entity` and exact `bridge_entry_id` are allowed.
The flow rechecks the saved snapshot, existing bridge filter and LocalTuya
role ownership. It requires two explicit confirmations: a verified HA backup
and the intention to restart HA manually.

On approval the **stored config entry** is updated, the staged proposal
is removed, and the wizard returns a **manual restart required** message.
The currently active accessory and HAP characteristic registrations remain
untouched *until restart*. It never invokes `async_reload`, changes bridge
configuration or forces a new Apple Home pairing.

**Important:** before the approved restart, a retry of
`async_setup_entry` with the new data must fail closed rather than silently
retargeting the running HomeKit accessory. Test the HA backup and a
disposable restart/rollback before any production canary.

## Repairs: original binding, not guessed replacements

If a saved UI entry cannot be set up because its LocalTuya mapping is
missing, changed or its existing HomeKit bridge cannot be found, the
integration raises a sanitized **Repairs** issue linked to the config
entry. Only a fixed issue type and entry reference are stored; no local
keys, IP/MAC addresses or HomeKit pairing information is logged.

The repair flow revalidates the **original** saved mapping. It cannot
guess replacement entities, bypass a bridge filter, take over a YAML
installation, control the device, or restart HA. The issue can be completed
only after the original LocalTuya entities and bridge are restored and
explicitly confirmed. If the config entry remains unavailable after
repair, manually restart HA using an approved procedure.

## Rollback and pending acceptance

Restore the previously tested HA configuration backup and restart under
owner control if a reconfigure caused an unexpected issue; do not hand-edit
Home Assistant's `.storage`, delete pairing state or reset the device.
Bridge migrations require a separate identity-preserving canary and are
**not enabled** by this feature.

The ROADMAP records V120-04 as accepted on 2026-11-23 using isolated real-HA APIs and regression tests. The actual production UI cutover and bridge migration remain separate, explicitly approved operations.
