<p align="center">
  <img src="assets/venta-aw730-banner.svg" alt="Venta AW730 air washer" width="100%" />
</p>

# Venta AW730

[![Validation](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant/actions/workflows/validate.yml)
[![Version 1.0.4](https://img.shields.io/badge/version-1.0.4-2ea44f)](https://github.com/dmitriy1ebedev/venta-aw730-homeassistant)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Apple HomeKit](https://img.shields.io/badge/Apple-HomeKit-111111?logo=apple&logoColor=white)](https://www.home-assistant.io/integrations/homekit/)
[![Yandex Alice](https://img.shields.io/badge/Yandex-Alice-FFCC00)](https://docs.yaha-cloud.ru/)
[![LocalTuya](https://img.shields.io/badge/LocalTuya-Tuya%203.4-2185D0)](https://github.com/xZetsubou/hass-localtuya)
[![RU / EN](https://img.shields.io/badge/README-RU%20%7C%20EN-5865F2)](README.ru.md)
[![MIT](https://img.shields.io/badge/license-MIT-00897B)](LICENSE)

[English](README.md) · [Русский](README.ru.md)

Connect the **Venta AW730 AeroStyle Compact** air washer to [Home Assistant](https://www.home-assistant.io/), [Apple Home / Siri](https://www.home-assistant.io/integrations/homekit/), and [Yandex Alice](https://docs.yaha-cloud.ru/). The complete Venta LocalTuya template **is bundled with this repository**; no separate template download is required.

## Features

Power, target humidity 30–70%, Auto / Manual / Sleep, five fan speeds, LED controls and sensors. A **single Apple Home accessory** with **Auto / Humidify / Off**.

## Installation

**1. Install [LocalTuya](https://github.com/xZetsubou/hass-localtuya).** The connection uses Tuya LAN protocol 3.4 and your own Smart Life / Tuya device credentials.

**2. Install Venta AW730 from Marketplace.**

<!-- ha-marketplace:exclude-start -->
[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dmitriy1ebedev&repository=venta-aw730-homeassistant&category=integration)
<!-- ha-marketplace:exclude-end -->

The [`venta_aw730.yaml` template](custom_components/venta_homekit_native/templates/venta_aw730.yaml) is included. Once Venta is configured and Home Assistant starts, the template is automatically made available in LocalTuya. Add the device with this template; do not download another one.

If you are adding the device **before** configuring the Venta HomeKit extension, register the template once with `python3 /config/custom_components/venta_homekit_native/install_localtuya_template.py` in the Home Assistant terminal (for Container installations, run it via `docker exec`).

**Updates:** after updating Venta through Marketplace and restarting Home Assistant, an unmodified managed LocalTuya template is synchronized automatically with a backup of the prior version. Customized templates are never overwritten. LocalTuya stores already configured device entities separately, so changes to their mappings must be reviewed; the update does not silently rewrite device credentials or entity IDs. HomeKit and Alice export the **same existing humidifier entity**, without a second Venta device.

**Apple Home:** configure an existing [HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/), add the [configuration example](examples/configuration.yaml.example) to `configuration.yaml` with your entity IDs, validate and restart HA. Do not recreate your working Venta accessory or pairing.

**Alice:** expose the same humidifier entity with [Yaha Cloud](https://docs.yaha-cloud.ru/) ([source](https://github.com/dext0r/yandex_smart_home)).

## Compatibility

Verified on one Venta AW730 Smart Life/Tuya 3.4 installation with LocalTuya 2026.10.0 and Home Assistant 2026.11.1. Other models and HA versions are not yet verified. See the [compatibility and troubleshooting matrix](docs/compatibility.md). The extension depends on internal HomeKit APIs and may need updates after major HA releases.

## License

MIT © Dmitriy Lebedev. Tuya mappings adapted from [Shinz2711](https://github.com/Shinz2711/venta-aw730-localtuya) (MIT; [attribution](THIRD_PARTY_NOTICES.md)).

Project: [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) · [Release process](docs/RELEASING.md) · [Diagnostic guide](docs/DIAGNOSTICS.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md)
