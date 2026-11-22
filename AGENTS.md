# Agent instructions — Venta AW730

Read [ROADMAP.md](ROADMAP.md), [README.md](README.md), [architecture](docs/architecture.md) and [security policy](SECURITY.md) before editing. These rules apply to the entire repository.

## Scope and compatibility

- The integration domain is `venta_homekit_native`. Do not rename it; installed Home Assistant systems depend on it.
- The Marketplace installs `custom_components/venta_homekit_native/`. It does **not** install LocalTuya.
- The bundled `templates/venta_aw730.yaml` is copied into LocalTuya **only on explicit user action**. Preserve the existing-template refusal and `--replace` backup behavior.
- HomeKit humidifier target modes are 0=Auto and 1=Humidify. Venta AW730 cannot dehumidify.
- Keep HomeKit pairing identities, exposed entity IDs, configured names and the existing bridge stable. Internal HA HomeKit/PyHAP APIs are not a public contract.
- Retain the original LocalTuya mapping attribution in `THIRD_PARTY_NOTICES.md`.

## Security and authorization

- Do not commit personal IP/MAC addresses, access credentials, Tuya local keys, tokens, account data, or HomeKit `.storage/` pairing files.
- Never query a user's live Home Assistant, toggle hardware, reset a HomeKit accessory or deploy without explicit authorization.
- Do not add hidden remote telemetry, external credential collection, or unnecessary network requests.
- Do not autonomously force-push, delete release history or rewrite public tags.

## Working method

1. Inspect status and preserve other changes.
2. Implement the smallest relevant fix and add regression coverage.
3. Run `python -m compileall -q custom_components tests scripts`.
4. Run `python -m unittest discover -s tests -v` and `python scripts/check_repository.py`.
5. Check HACS/Marketplace and hassfest workflow results; a workflow file alone is not a passing check.
6. For releases, follow [docs/MAINTAINING.md](docs/MAINTAINING.md), verify GitHub and GitVerse contain the same files, and distinguish published code from installed code.

Be precise about what was tested: offline checks, a disposable HA instance, and a real Venta installation are different levels of evidence.
