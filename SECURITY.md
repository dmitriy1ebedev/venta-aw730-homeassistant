# Security policy

## Supported versions

Security fixes target the latest published version of Venta AW730. Earlier releases may not receive separate patches.

## Reporting a vulnerability

Please **do not open a public issue** containing exploit details, access tokens, Tuya local keys, HomeKit pairing data or personal network details.

If available, use [GitHub's private vulnerability reporting](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/security/advisories/new). If the private reporting option is unavailable, [open a minimal issue asking for a secure contact method](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/issues/new/choose) without disclosing the vulnerability.

Maintainers will assess impact, coordinate a fix and credit the reporter with permission. No fixed response or disclosure deadline is promised.

## Security boundaries

The project connects a LocalTuya entity to Home Assistant's HomeKit bridge. The HomeKit extension uses internal Home Assistant interfaces; changes may break compatibility. Never submit a production `.storage/` directory or real device credentials as a reproduction. See [AGENTS.md](AGENTS.md) for agent safety constraints.
