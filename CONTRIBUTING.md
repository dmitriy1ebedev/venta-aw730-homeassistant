# Contributing to Venta AW730

Issues and pull requests are welcome. Check the [README](README.md), [security policy](SECURITY.md) and existing issues first.

## Bug reports

Read the [verified compatibility matrix](docs/compatibility.md) before reporting a device as supported. Use the [bug report form](.github/ISSUE_TEMPLATE/bug_report.yml). Include the Venta, Home Assistant, LocalTuya and Tuya protocol versions; for Apple Home problems, add the iOS version. Describe the steps, expected result, actual result and the layer affected: Tuya LAN, LocalTuya, Home Assistant, HomeKit, Alice or dashboard. Redact screenshots and logs: no Tuya keys, HomeKit pairing secrets, IP/MAC addresses or account details.

Security vulnerabilities must not be reported publicly; see [SECURITY.md](SECURITY.md).

## Pull requests

1. Fork the repository, make one focused change and describe its purpose.
2. Preserve the integration domain, HomeKit accessory identity and existing pairing.
3. Add a regression test for changed behavior.
4. Run `python -m unittest discover -s tests -v`, `python -m compileall -q custom_components tests scripts` and `python scripts/check_repository.py`.
5. Explain compatibility, manual testing, failure modes and rollback in the PR.

Do not silently replace a modified LocalTuya template or reset a HomeKit bridge. Do not add secrets, telemetry, binary artifacts unrelated to branding, or any code that operates on another user's hardware.

See [AGENTS.md](AGENTS.md) and [maintainer guide](docs/MAINTAINING.md).
