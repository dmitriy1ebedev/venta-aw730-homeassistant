# Venta dashboard / Панель Venta

Optional standalone Lovelace assets. Installation is manual and does not replace
the HomeKit integration, LocalTuya, device mappings, recorder settings or the
default Home Assistant dashboard. No additional account, CDN or telemetry.

1. Copy `venta-airwasher-card.js` into the HA `www` directory and register
   `/local/venta-airwasher-card.js` as a dashboard JavaScript module.
2. Add a manual Lovelace card using [example.yaml](example.yaml). Replace every
   placeholder with entities belonging to the intended physical Venta.
3. Omit optional PM2.5 and water level roles and their graph entries when the
   device does not expose those sensors. Missing samples remain unavailable.
   Set a helper role to null to disable it. The original AW730 entity retains
   its legacy defaults; a different humidifier never inherits those defaults.
4. The native [HA history graph](https://www.home-assistant.io/dashboards/history-graph/)
   reads the existing local recorder. It does not create a database or change
   retention. If a sensor is excluded from recorder, no history is fabricated.
   Numeric readings are graphed; select fan speed is a state timeline.

The card's controls use the currently available Home Assistant service and
option list. When the device is unavailable or a command is in flight, controls
are disabled; status is read back from HA rather than predicted. Units come
from the linked sensor. The optional more-info override remains separate and
hardcoded for humidifier.venta_aw730 until edited; do not install it just to
use this card.

## По-русски

Скопируйте JS в каталог `www` Home Assistant, добавьте ресурс
`/local/venta-airwasher-card.js` типа «JavaScript-модуль», затем создайте
ручную карточку по [example.yaml](example.yaml). Замените все ID на сущности
своей мойки. Если PM2.5 или уровень воды отсутствуют, удалите соответствующие
поля и строки графиков; значение null отключает вспомогательную сущность.
Графики за 24 часа штатные, используют историю HA. Скорость вентилятора,
представленная select, отображается как история состояний. Никакой внешней
регистрации, автоматического изменения recorder или облачной отправки данных.
Оверрайд more-info не нужен для работы панели.

## Verification

The browser fixture in `tests/dashboard_browser.html` uses synthetic HA states
and service calls, not a live HA server. CI checks narrow 320px and desktop
700px layouts, labels, keyboard focus, unsupported options, offline and
in-flight guards, actual configured entity routing and redacted errors.
This is not evidence of physical iPhone/Safari or a live HA dashboard test.
