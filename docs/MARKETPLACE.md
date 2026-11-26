# Marketplace catalog status / Статус общего каталога

Assessment date: 2026-11-26. **NOT SUBMITTED**; no claim of catalog acceptance.

| Criterion | Observed evidence / decision |
|---|---|
| Public GitHub repository and integration structure | Public repository, one custom integration and hacs.json; custom-repository installation path documented. |
| Full release | GitHub Release v1.2.0 published 2026-11-23. Source changes after that tag are not a new release. |
| Validation | GitHub Actions 45762243321 (7/7 PASS), GitVerse 2223148 PASS. HACS action uses `ignore: topics`; GitHub topics were empty when inspected. This does not meet the no-ignores catalog prerequisite. |
| Core extension eligibility | Venta uses its own integration domain but redirects the internal HomeKit humidifier type registry. The official catalog excludes integrations that replace core integrations. The scoped patch may fall under that restriction; eligibility is not established without a maintainer decision or a supported extension architecture. |
| Application | No matching pull request found in hacs/default by repository name. Do not submit as eligible or claim acceptance until the two outstanding prerequisites are resolved. |

Official rules: [catalog admission](https://contributors.home-assistant.io/marketplace/guides/catalog/),
[custom integration publishing](https://contributors.home-assistant.io/marketplace/guides/integrations/),
[custom repository installation](https://www.home-assistant.io/integrations/marketplace/#custom-repositories).

## Installation now

Use the custom GitHub repository link in Settings → Marketplace → Add from link.
Custom repository installation requires a GitHub connection; it does not make
the repository an accepted default. LocalTuya must be installed separately.
Use the tested published version and keep the existing HomeKit bridge.

## Дальнейшая подача

До заявки необходимо согласовать допустимость архитектуры с сопровождающими
каталога либо перейти на поддерживаемый механизм расширения HomeKit, добавить
темы репозитория, пройти HACS action без исключений и hassfest на точном
кандидате, затем опубликовать новый полный выпуск. Только владелец или
существенный участник может подать PR в hacs/default. После подачи фиксируются
ссылка и фактическое решение; зелёный CI не означает одобрение.

Сейчас доступна установка по ссылке как пользовательской интеграции.
Принудительно заменять HomeKit, удалять сопряжения или ослаблять проверки
ради допуска в каталог нельзя.
