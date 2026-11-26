# Model profiles / Профили моделей (V130-03)

The immutable `model_profiles.py` describes the bundled AW730 Tuya LAN 3.4
mapping and the existing fan/LED level conversions. It performs no discovery,
network calls, storage writes or device commands. The current integration
still targets the same explicitly configured AW730 entity and bridge; the
profile lookup is not automatic hardware detection and does not rewrite
existing configuration. No model selector is added to the UI.

| Model | Protocol | Evidence | State |
|---|---|---|---|
| AW730 (Smart Life/Tuya variant) | 3.4 | One physical unit previously verified, bundled template and CI; exact firmware not independently recorded | Existing supported combination; not a universal firmware claim |
| AW735 | Unconfirmed | Manufacturer lists it in the AeroStyle Compact family; no owner DP/command evidence | **UNVERIFIED — no active profile or template** |
| Other AW7xx, AP/AH variants | Unconfirmed | No relevant repeatable physical evidence | **UNVERIFIED** |
| Other Tuya protocol or native Venta transport | Unconfirmed | Not implemented/tested | **UNSUPPORTED** |

`get_profile("AW730", "3.4")` returns the single known contract.
No fallback for different model, spelling or protocol. The firmware field is
unknown, not a wildcard certification. The profile has 18 entity mappings;
DP13/14 are shared with the humidifier's target/current attributes, and DP24
is its mode attribute. The template's exact SHA-256 is pinned and CI checks
role order, IDs, mode/option values, units, bounds and reconnect settings.
Existing LocalTuya YAML bytes, public entity names and HAP service IDs are
unchanged. The existing three diagnostic reset buttons remain unverified;
the profile does not enable or invoke them. Mapping metadata alone is not
permission to write a DP.

## Release scope and deferred hardware work

The 1.3.0 model scope is the existing AW730 combination, not a promise of
additional device support. The second-model hardware acceptance remains
unperformed because a suitable device/evidence is unavailable. Track this
separately in [issue #41](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/issues/41).
The original physical criterion must not be recorded as a successful test.
Unknown model/protocol pairs remain unsupported until the evidence below is
obtained.

## Evidence before adding another model

1. Record printed model, firmware **version**, Tuya LAN protocol, HA and
   LocalTuya versions. Do not include serial number, cloud ID, address, keys
   or production configuration.
2. Provide redacted observations of DP ID, data type, unit/scale, allowed
   enum values, read/write behavior and observed state. An unknown field
   stays unknown; never infer a DP from another model. A read-only discovery
   or manual inspection is not proof of command behavior.
3. With separate owner consent, test reversible ordinary commands one at a
   time from a recorded initial state, confirm device and HA readback, and
   restore the initial state. Do not reset maintenance counters or pairings
   as part of ordinary tests. No automatic probing.
4. Add an isolated model-specific contract, explicit template and regression
   tests. Require actual read/command evidence and review before listing the
   model as supported. Test AW730 compatibility independently.

## По-русски

Профиль AW730 выделяет карту DP и числовые параметры в неизменяемую
структуру. Он не определяет модель автоматически и не меняет существующие
сущности, настройки, мост и сопряжение. AW735 пока только кандидат.
Для новой модели необходимы версия прошивки, обезличенные наблюдения DP
(тип, значение, единица и допустимые варианты), реальная проверка команд с
обратным чтением и отдельное разрешение владельца. Секреты и резервные
копии не публикуются. Сбросы счётчиков — отдельная процедура.
См. [матрицу совместимости](compatibility.md) и
[форму обращения](../.github/ISSUE_TEMPLATE/bug_report.yml).

Manufacturer product reference (not DP evidence):
https://www.venta-air.com/en_nl/AW735-Hybrid-AeroStyle-Compact-Airwasher/8076500
