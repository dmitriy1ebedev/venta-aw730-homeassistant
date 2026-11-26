# Apple Home and Alice / Apple Home и Алиса (V130-04)

This document describes the 1.3.0 source candidate. It is not evidence of a
production installation or successful voice-command acceptance.

## One physical device, existing identities

Use one existing Home Assistant humidifier as the physical Venta's control
entity. Export it once in the existing HomeKit bridge and once in the
existing Yaha Cloud integration. Do not export an additional generic
humidifier for the same device. Linked HomeKit fan, Auto, LED and temperature
services keep their existing service IDs and names; they are not separate
physical air washers. The HomeKit target exposes only Auto/Humidify, not
Dehumidify. Sleep remains an existing LocalTuya/HA mode and is not represented
as a third HomeKit target state. Alice's available capabilities depend on
Yaha Cloud and must be observed, not inferred from HomeKit metadata.

## Candidate command guard

The HomeKit adapter validates all supplied fan/LED characteristics before
the first service dispatch. NaN, infinity, invalid binary states and out-of-
range percentages are rejected. The fan adapter refuses all commands when
the humidifier has no known on/off state, including turn-off. An explicit
Auto request takes priority over a positive speed in the same fan write:
do not send a manual speed alongside it. Explicit off/zero speed retains
the existing turn-off behavior. The physical automatic control algorithm,
Sleep mode semantics, LED option mapping and existing accessory identity
are not changed. A service call returning successfully does not establish
physical readback; no new claim of confirmed device state is made.

## Owner-authorized acceptance (not yet executed)

Before testing, record the current mode, power, target RH, fan and LED
settings locally. Confirm backup and rollback readiness, without publishing
private IDs, pairing data or configuration. Check the following on the actual
device and in HA, then in each platform; record PASS/FAIL/PENDING and observed
readback, not merely a successful app button or voice response.

| Check | Expected evidence |
|---|---|
| Existing exports | One physical Venta in Apple Home and one in Alice; same underlying HA entity; names and pairing unchanged |
| Power | On/off agrees with HA and device; no duplicate or contradictory action |
| Target humidity | A supported value in 30–70% is observed, then prior setting restored |
| Auto/Manual | Explicit Auto and Manual agree with HA; manual fan speeds select the intended existing role |
| Sleep | HA Sleep remains unchanged unless deliberately commanded; platform display is documented accurately |
| LED | Only supported power and brightness controls, verified by observed state |
| Unavailable | No command from the guarded fan path; no false claim of physical success |
| Restore | Restore initial reversible settings; no reset or re-pairing; existing unrelated accessories remain unchanged |

Do not use real device commands, a production restart or a counter reset
without the owner's separate approval. No new routine automation or
cross-platform re-export is activated as part of this candidate.

## По-русски

Apple Home и Алиса должны управлять одной исходной сущностью увлажнителя HA
через уже существующие интеграции. Связанные сервисы вентилятора, «Авто»,
подсветки и температуры не создают вторую физическую мойку. Для приёмки
нужны реальные команды и обратное чтение состояния, сохранение имён,
сопряжения и прежней конфигурации. Недоступность и конфликтующие запросы
проверяются отдельно. Сценарии Auto/Sleep не должны бороться друг с другом.
До согласованной аппаратной проверки результаты CI остаются изолированными
регрессиями, а не подтверждением работы Алисы или Apple Home на телефоне.
