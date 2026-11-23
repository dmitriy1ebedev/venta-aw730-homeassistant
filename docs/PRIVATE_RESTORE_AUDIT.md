# Venta V120-06 — private backup restore audit

This source-only gate verifies a **native Home Assistant Container backup**
without uploading its contents or interrupting the running installation.

`scripts/ha_private_restore_audit.py` streams a native outer TAR plus
`homeassistant.tar.gz`, checks its backup manifest, selects exactly six
required files (YAML, config entries, Venta manifest, HomeKit AID/IID maps and
pairing state for one existing bridge), and restores those files inside an
exclusive temporary directory. In production run that directory is on
`/dev/shm` (RAM-backed tmpfs), with directory mode 0700 and file mode 0600.
The directory is removed on exit, including on mismatch. All six extracted
files must match the running installation byte-for-byte, and HomeKit must
retain real paired-client and key material.

The tool prints only counts and status. It never prints a local key,
HomeKit private key, MAC, paired client ID, raw config, or source SHA; it
never invokes HA APIs or sends data to GitHub. Archive paths are not used
to construct output paths, so untrusted member names cannot escape the
temporary directory. Symlinks, duplicate allowlisted members, missing
files and unexpected file sizes are rejected.

Example (run locally on the HA host, not in CI):

```sh
python3 scripts/ha_private_restore_audit.py \
  --backup /path/to/verified-native-backup.tar \
  --live-root /opt/homeassistant/config \
  --bridge-entry-id EXISTING_BRIDGE_ENTRY_ID \
  --scratch-root /dev/shm
```

A production result `status=PASS` confirms the backup is *intact for the
selected six files at the time of the check*. The separate complete
Home Assistant restart test and successful physical LocalTuya-to-HomeKit
migration are **not** covered; passing this audit never authorizes an
automatic restart, pairing reset, deployment or YAML removal. Backup
retention, snapshot encryption and off-host redundancy require their own
operator policy.

Synthetic negative tests are executed by normal Python CI; no real
`.storage` files are committed to Git or sent to any CI provider.
