<p align="center">
  <img src="assets/venta-aw730-banner.svg" alt="Мойка воздуха Venta AW730" width="100%" />
</p>

# Venta AW730

[![Проверки CI](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/workflows/validate.yml)
[![Версия 1.2.0](https://img.shields.io/badge/version-1.2.0-2ea44f)](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Apple HomeKit](https://img.shields.io/badge/Apple-HomeKit-111111?logo=apple&logoColor=white)](https://www.home-assistant.io/integrations/homekit/)
[![Алиса](https://img.shields.io/badge/Yandex-Alice-FFCC00)](https://docs.yaha-cloud.ru/)
[![LocalTuya](https://img.shields.io/badge/LocalTuya-Tuya%203.4-2185D0)](https://github.com/xZetsubou/hass-localtuya)
[![RU / EN](https://img.shields.io/badge/README-RU%20%7C%20EN-5865F2)](README.md)
[![MIT](https://img.shields.io/badge/license-MIT-00897B)](LICENSE)

[Русский](README.ru.md) · [English](README.md)

Подключение мойки воздуха **Venta AW730 AeroStyle Compact** к [Home Assistant](https://www.home-assistant.io/), [Apple Home / Siri](https://www.home-assistant.io/integrations/homekit/) и [Алисе](https://docs.yaha-cloud.ru/). **Весь шаблон Venta уже в этом репозитории** — отдельно скачивать шаблон с другого GitHub не нужно.

## Что умеет

Питание, влажность 30–70%, режимы Авто / Ручной / Сон, пять скоростей вентилятора, подсветка и датчики. В Apple Home — одно устройство с переключателем **«Авто / Увлажнение / Выкл.»**.

## Установка

**1. Установите [LocalTuya](https://github.com/xZetsubou/hass-localtuya).** Он подключает мойку локально по протоколу Tuya 3.4. Для добавления устройства потребуются ваши данные подключения из Smart Life / Tuya.

**2. Добавьте Venta AW730 как пользовательский репозиторий Marketplace.** В HA 2026.11+ откройте «Настройки → Marketplace → Добавить по ссылке», введите `dmitriy1ebedev/venta-aw730-homeassistant` и при необходимости выберите тип «Интеграция». Для пользовательского репозитория требуется подключение GitHub. Это не публикация в общем каталоге; см. [статус допуска](docs/MARKETPLACE.md). Выберите опубликованный выпуск, а не ветку разработки.

<!-- ha-marketplace:exclude-start -->
[![Добавить в Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dmitriy1ebedev&repository=venta-aw730-homeassistant&category=integration)
<!-- ha-marketplace:exclude-end -->

Шаблон [`venta_aw730.yaml`](custom_components/venta_homekit_native/templates/venta_aw730.yaml) уже в комплекте. После настройки Venta и запуска Home Assistant он автоматически появляется в LocalTuya. Добавьте устройство и выберите этот шаблон — скачивать его отдельно не нужно.

Если вы добавляете устройство **до** настройки расширения Venta для HomeKit, один раз зарегистрируйте шаблон командой `python3 /config/custom_components/venta_homekit_native/install_localtuya_template.py` в терминале Home Assistant (для Container — через `docker exec`).

**Обновления:** после установки новой версии Venta через Marketplace и перезапуска Home Assistant неизменённый шаблон LocalTuya синхронизируется автоматически, прежняя копия сохраняется. Пользовательский шаблон не перезаписывается. Конфигурации ранее добавленных устройств хранятся в LocalTuya отдельно; изменения их сопоставлений требуют проверки. Учётные данные и идентификаторы сущностей автоматически не переписываются. Apple Home и Алиса используют **ту же существующую сущность увлажнителя**, без второго устройства.

**Apple Home:** используйте существующий [HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/). При новой настройке Venta 1.2.0 откройте «Настройки → Устройства и службы → Добавить интеграцию → Venta AW730», выберите существующий увлажнитель LocalTuya, мост и пять связанных сущностей. Альтернатива — [пример YAML](examples/configuration.yaml.example): подставьте свои ID, проверьте конфигурацию и перезапустите HA. Используйте только один способ настройки. Рабочую YAML-конфигурацию сохраняйте, если не решили выполнить [миграцию с проверенным резервным копированием](docs/YAML_MIGRATION.md). Не удаляйте существующую Venta и сопряжение HomeKit.

**Алиса:** экспортируйте ту же сущность увлажнителя через [Yaha Cloud](https://docs.yaha-cloud.ru/) ([исходники](https://github.com/dext0r/yandex_smart_home)).

## Совместимость

Проверена одна Venta AW730 Smart Life/Tuya 3.4 с LocalTuya 2026.10.0 и Home Assistant 2026.11.1. HA 2026.11.2, 2026.11.3 и 2026.12.0b0 проверены только в изолированном CI; другие модели и непроверенные версии HA не подтверждены. См. [матрицу совместимости и диагностику](docs/compatibility.md). Расширение HomeKit зависит от внутренних API Home Assistant; после крупных обновлений может понадобиться адаптация.

## Дополнительная панель и поддержка

[Самостоятельная панель](extras/dashboard/README.md) — ресурс разработки для ручной установки, не входящий в выпущенный пакет интеграции. При ошибке используйте [диагностику только для чтения](docs/DIAGNOSTICS.md) и [форму обращения](.github/ISSUE_TEMPLATE/bug_report.yml). Не отправляйте ключи и файлы сопряжения, не сбрасывайте устройство для диагностики.

## Лицензия

MIT © Dmitriy Lebedev. Сопоставления Tuya адаптированы из проекта [Shinz2711](https://github.com/Shinz2711/venta-aw730-localtuya) (MIT; [атрибуция](THIRD_PARTY_NOTICES.md)).

Проект: [Дорожная карта](ROADMAP.md) · [История изменений](CHANGELOG.md) · [Процедура выпуска](docs/RELEASING.md) · [Диагностика](docs/DIAGNOSTICS.md) · [Участие](CONTRIBUTING.md) · [Безопасность](SECURITY.md) · [Правила сообщества](CODE_OF_CONDUCT.md)
