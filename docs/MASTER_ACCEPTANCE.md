# Venta 1.2.0 — isolated master acceptance evidence (V120-05)

**Candidate only: not installed or accepted.** The existing 1.0.4
installation, HomeKit pairing, Yandex export and LocalTuya device
remain unchanged while this validation runs.

## Independent-process identity gate

GitHub Actions uses two actual Home Assistant images, 2026.11.1 and
2026.11.2. Each job stages a fresh *synthetic* Venta configuration
from the reviewed component-only archive. Every smoke container uses
`--network none`, `--cap-drop ALL`, `no-new-privileges`, explicit
CPU/memory limits and disposable files. No HomeKit server is started.

For each version a new cross-process gate uses real HA/PyHAP
`AccessoryAidStorage`, `AccessoryIIDStorage`, `HomeDriver` and
native humidifier classes in two **different** container processes:

1. The capture process allocates AID/IID and the service/characteristic
   structure for a synthetic Venta and an unrelated native humidifier.
   It writes only synthetic allocation metadata and an SHA-256
   fingerprint to the runner's temporary state volume, never to
   Home Assistant `.storage` or any pairing file.
2. The verify process recreates both accessories using exactly the
   captured allocation maps and checks that both AIDs and the entire
   service/characteristic IID structures match. All native HomeKit
   classes are restored in the test process, including unrelated
   accessories. A changed AID/IID or corrupted state must fail CI.

The existing same-process replay and official config-entry setup,
Options, Reconfigure, Repairs and registry smoke checks continue to
run. A passing capture alone is **not** a passing cross-process gate.

## Synthetic YAML snapshot rollback rehearsal

Both HA-version CI jobs also operate on the exact, publicly known
`FAKE_HA_CONFIG` source fixture, not the owner's data. A separate temporary
snapshot captures its original `configuration.yaml` bytes and SHA-256,
and the rehearsal removes only the fake `venta_homekit_native:` block.
The test writes a **separate synthetic config-entry proposal** outside HA's
`.storage`, verifies `check_config` of the cutover fixture in the real HA
container, then restores the original YAML byte-for-byte and validates it
with `check_config` again. Missing or corrupted backups, modified YAML,
symlinks and tampered staged entries cause fail-closed errors. No actual
config entry is installed by this rehearsal.

## Acceptance gap and rollback

This gate does **not** exercise Home Assistant's actual persisted config
entry manager across a full boot/restart, a real Apple Home pairing, or
a restore of the owner's configuration snapshot. It exercises internal
HomeKit identity allocation with synthetic data only. Therefore it is
incorrect to claim that a green CI run proves production migration or
grants permission to restart HA.

Before completing V120-05, require a **separate disposable** HA startup
from a sanitized snapshot, YAML-to-UI migration and genuine restored
snapshot/restart, acceptance of original HomeKit AID/IID and other
accessories, both RU/EN wizards, and an **owner-approved canary** with
verified rollback readiness. Any changed identity, duplicate
humidifier, failed setup or unrecognized HA API must block rollout.
Never remove `.storage`, reset Apple Home or silently take over an
existing LocalTuya device to work around a failed test.

Production rollback, if explicitly approved for a future canary,
restores the verified pre-upgrade HA snapshot and original seven-key
YAML configuration without resetting the paired HomeKit bridge.
Do not replace installed files, publish a production release or
change any physical device as part of these CI tests.
