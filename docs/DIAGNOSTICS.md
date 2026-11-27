# Venta AW730 — privacy-safe diagnostics

The diagnostic service is included in published Venta 1.2.0. The older 1.0.4 rollback baseline does not provide it. See [release evidence](RELEASE_1_2_0.md). If the service is absent, verify the installed version rather than restarting, upgrading or resetting devices solely for diagnosis.

## How to collect a diagnostic report after an approved release

In Home Assistant, open **Developer Tools → Actions** and select
`venta_homekit_native.log_diagnostics`. Run it once to see the JSON response
in Developer Tools. If integration INFO logging is enabled, the same report is
also written to the Home Assistant log as `Venta diagnostic status:`; the
response does not depend on logger verbosity. The service is read-only:
it does **not** issue Tuya commands, reconnect devices, start a new HomeKit
server, reset service counters or modify pairings.

The output is a single JSON object with a **fixed schema**:

- `schema`: diagnostic schema version, currently `1`
- `integration_version`, `home_assistant_version`, `localtuya_version`: sanitized version strings or `unknown`
- `configuration`: `complete` or `incomplete` (presence of the six entity references and bridge entry)
- `localtuya`: `loaded`, `not_loaded`, `not_configured` or `unknown`
- `humidifier`: `on`, `off`, `unavailable`, `unknown`, `missing`, `not_configured` or `other`
- `linked_entities`: only availability statuses for fan, LED, brightness, temperature and humidity
- `homekit_bridge`: `ready`, `not_ready`, `not_found`, `not_configured` or `unknown`
- `recommendation`: one of the codes below
- `protocol_error`: currently always `not_available_from_entity_state`; the service **cannot** infer Tuya handshake failures from entity states alone

**No device identifiers, entity IDs, IP/MAC, token, local_key, pairing information, raw attributes or sensor measurements are included.** Diagnostics are generated locally and written to the HA log only when the service is called; no external telemetry.

## Synthetic example (not a report from a real installation)

```json
{
  "schema": 1,
  "integration_version": "1.3.0",
  "home_assistant_version": "2026.11.1",
  "localtuya_version": "2026.10.0",
  "configuration": "complete",
  "localtuya": "loaded",
  "humidifier": "off",
  "linked_entities": {
    "fan": "available", "led": "available", "brightness": "available",
    "temperature": "available", "humidity": "available"
  },
  "homekit_bridge": "ready",
  "recommendation": "none",
  "protocol_error": "not_available_from_entity_state"
}
```

This fixture is compared with the actual diagnostic function by CI. A beta version string can appear as `unknown` because the sanitizer accepts numeric versions only; include the HA version separately in the issue form.

## По-русски

В HA откройте «Инструменты разработчика → Действия», выберите `venta_homekit_native.log_diagnostics` и выполните один раз. Скопируйте JSON-ответ после проверки на отсутствие личных данных. При недоступности соберите отчёт во время ошибки и после восстановления; сравните категории. Не вызывайте reset, не удаляйте мост и не меняйте параметры LocalTuya для получения отчёта. Укажите версии и краткие обезличенные шаги в [форме ошибки](../.github/ISSUE_TEMPLATE/bug_report.yml). Диагностика не определяет причину ошибки протокола по одному статусу unavailable.

## Recommendations

| Code | Safe next step |
|---|---|
| `none` | No problem visible in the current snapshot; this does not rule out intermittent failures |
| `review_venta_configuration` | Check the seven Venta YAML keys and the existing bridge title, without recreating HomeKit |
| `check_localtuya_configuration` | LocalTuya has no config entry; check whether it is configured (this alone does not mean not installed) |
| `check_localtuya_load_state` | Existing LocalTuya config entry is not loaded; review its HA integration error before changing it |
| `check_localtuya_connection_logs` | The humidifier is missing/unavailable/unknown; inspect redacted LocalTuya coordinator logs and confirm one LAN client |
| `check_existing_homekit_bridge` | Check the existing HomeKit Bridge runtime; avoid unpairing/recreating it |
| `check_missing_linked_entities` | Some fan, LED, brightness or sensor entities are not available; check LocalTuya device configuration first |

For intermittent outages, collect one status while disconnected and another after
recovery. Compare only the status categories. Correlate with **redacted** LocalTuya
logs and router observations from the same interval. The service does **not**
keep an outage history or automatically identify the origin of a handshake
timeout. A router showing a device online does not prove that Tuya LAN is
responding.

## Regression coverage and scope

`tests/test_diagnostics.py` validates missing LocalTuya, unloaded entries,
unavailable/missing entities, incorrect configuration, bridge startup and
reconnect, malformed manifest versions, private data redaction and absence of
service calls. The service-registration test exercises actual
`venta_homekit_native.async_setup` against isolated HA stubs.

A passing unit test or isolated Home Assistant CI run is **not** evidence that
this service has been installed or executed on a live HA system.

For the 2026-11-22 LocalTuya handshake incident see
[issue #6](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/issues/6).
For release compatibility consult [compatibility.md](compatibility.md).
