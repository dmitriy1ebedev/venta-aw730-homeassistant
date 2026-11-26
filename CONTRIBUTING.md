# Contributing to Venta AW730

Issues and pull requests are welcome. Check the [README](README.md), [security policy](SECURITY.md) and existing issues first.

## Bug reports

Read the [verified compatibility matrix](docs/compatibility.md) before reporting a device as supported. Use the [bug report form](.github/ISSUE_TEMPLATE/bug_report.yml). Include the Venta, Home Assistant, LocalTuya and Tuya protocol versions; for Apple Home problems, add the iOS version. Describe the steps, expected result, actual result and the layer affected: Tuya LAN, LocalTuya, Home Assistant, HomeKit, Alice or dashboard. Redact screenshots and logs: no Tuya keys, HomeKit pairing secrets, IP/MAC addresses or account details.

For new models provide the printed model, firmware version and redacted DP type/value observations. Do not assume the AW730 map fits another model. Physical command readback needs the owner's consent; reset is a separate test. Use the [diagnostic example](docs/DIAGNOSTICS.md) and never attach production backup files.

Security vulnerabilities must not be reported publicly; see [SECURITY.md](SECURITY.md).

## Участие и сообщения об ошибках

Сначала проверьте [совместимость](docs/compatibility.md). Укажите модель, версии HA, Venta и LocalTuya, воспроизводимые шаги, ожидаемый и фактический результат. Для новой модели нужны обезличенные наблюдения DP, а не копия ключей или конфигурации. Не меняйте сопряжение и не сбрасывайте счётчики ради воспроизведения. Для исправления добавьте регрессионный тест и опишите откат. Вопросы безопасности направляйте по [правилам](SECURITY.md).

## Pull requests

1. Fork the repository, make one focused change and describe its purpose.
2. Preserve the integration domain, HomeKit accessory identity and existing pairing.
3. Add a regression test for changed behavior.
4. Run `python -m unittest discover -s tests -v`, `python -m compileall -q custom_components tests scripts` and `python scripts/check_repository.py`.
5. Explain compatibility, manual testing, failure modes and rollback in the PR.

Do not silently replace a modified LocalTuya template or reset a HomeKit bridge. Do not add secrets, telemetry, binary artifacts unrelated to branding, or any code that operates on another user's hardware.

See [AGENTS.md](AGENTS.md) and [maintainer guide](docs/MAINTAINING.md).
