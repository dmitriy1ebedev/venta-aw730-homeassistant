# Maintaining and publishing Venta AW730

This document is for maintainers, not an installation step.

## Repositories

- Canonical Marketplace source: https://github.com/dmitriy1ebedev/venta-aw730-homeassistant
- Additional public mirror: https://gitverse.ru/dmitriy_1ebedev/venta-aw730-homeassistant

Keep the same release content in both public repositories. The Marketplace retrieves code from GitHub, not from GitVerse.

## Before publishing

1. Verify the local Git worktree is clean and the changes are intentionally reviewed.
2. Run `python -m unittest discover -s tests -v` and `python scripts/check_repository.py`.
3. Check `SECURITY.md`, third-party MIT attribution and the package for accidental secrets.
4. Review the GitHub **CI**, HACS validation and hassfest workflow results. A committed workflow is not proof it passed.
5. If runtime code changed, test in an isolated Home Assistant and check paired HomeKit accessory identity; never use the user's living setup as an automated test.
6. Update the integration's manifest version and `CHANGELOG.md` when releasing code.
7. Publish a matching GitHub release tag (e.g. `v1.0.2`) after validation. Marketplace may install the latest release or the default branch depending on repository settings. Check the effective version in the Marketplace.
8. Mirror the reviewed content to GitVerse, then verify the file tree hashes or bytes match.

## Git history and releases

Normal PRs and commits should remain auditable. Rewriting a public branch is exceptional, requires explicit authorization and a compare-and-swap ref check; it cannot erase previously cloned objects or provider caches. GitVerse may reject history rewrites even when normal pushes work.

## Updating the bundled LocalTuya template

A Marketplace update replaces the integration folder. The separate installed LocalTuya template is intentionally not overwritten. After template changes, users may rerun `install_localtuya_template.py`; differing existing templates require `--replace` and a backup. Test both paths.

## CI expectations

- Python tests and publication structure checks pass.
- HACS repository validation is green.
- hassfest is green, or its failures are documented and addressed.
- No production secrets, personal configuration or HomeKit pairings appear in tracked files or archives.

## Marketplace catalog

Installing a custom repository is separate from being accepted into the default catalog. The project currently extends internal HomeKit behavior, which may restrict default catalog eligibility. See [Home Assistant contributor guidance](https://contributors.home-assistant.io/marketplace/guides/integrations/).
