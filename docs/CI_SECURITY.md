# CI and supply-chain review — Venta AW730

Review baseline: 2026-11-22, local source after P01.1/P01.4, no device-side changes. This document separates verified controls from unresolved provider/Marketplace limitations. It is not a substitute for a secret scan of every historical commit or a live Home Assistant test.

## CI protections found

| Control | Observed configuration | Interpretation |
|---|---|---|
| GitHub Actions token | `permissions: contents: read` at workflow root | Read-only workflow token by default |
| Source checkout | `persist-credentials: false` | Checkout does not leave a write credential behind |
| Dependencies | `actions/checkout`, `setup-python`, `hacs/action`, `hassfest` pinned to 40-character commit digests | Maintainer must review changes before updating a digest |
| Python | Syntax check, `unittest`, `scripts/check_repository.py` | Offline code and release structure checks |
| JavaScript | Two dashboard files checked with Node syntax parser | Does not prove the UI behaves correctly in a browser |
| Release layout | `scripts/build_release.py` and `tests/test_release_package.py` | Reproducible source package and isolated install-layout smoke; **not** real HA runtime |
| Home Assistant / HACS | HACS, hassfest and an isolated Home Assistant 2026.11.1 container smoke run on GitHub runners | The container validates a synthetic YAML config from the exact packaged component; it cannot prove HomeKit pairing, physical-device control, or production startup |
| Attribution | `LICENSE` and `THIRD_PARTY_NOTICES.md` include upstream MIT license of adapted LocalTuya YAML | Keep notices when changing the template |

## Known limitations and open work

1. The HACS step intentionally has `ignore: topics`. This is a **documented exception for a custom repository**, not compliance with default HACS catalog admission. Remove only after verifying GitHub Topics and running the full HACS check without an ignore. It must not be described as an official/default catalog listing.
2. Public GitVerse mirror has lagged behind GitHub since the earlier 1.0.4 work. The verified GitVerse run `2180839` passed at `4ef7855`; later GitHub runs refer to different source trees. Until the current tree is pushed through an authorized route and its GitVerse CI passes, P01.3 cannot be accepted as complete.
3. No GitHub Release/tag was present at the start of this review. Releasing requires the procedure in [RELEASING.md](RELEASING.md), not merely a version badge or manifest field.
4. The repository regex-based credential check catches common explicit assignments, but cannot prove historic or encoded secrets are absent. No blanket claim of a complete secret audit is made. Do not include `.storage`, pairing data, Tuya local keys, private IP/MAC or personal user configs.
5. GitHub Actions `ubuntu-latest` and Python 3.14 test runners are not the installed HA runtime. Internal HomeKit/PyHAP monkey-patching is a compatibility risk; isolate and test it before runtime releases.
6. CI workflow only checks JavaScript syntax, not interaction, accessibility, or visual regressions; these remain future roadmap work.

## Expected evidence for P01.3

- The exact current local tree and both provider tree hashes match.
- Python, repository, JavaScript, HACS and hassfest tests on compatible runners finish PASS and have exact run IDs and SHAs.
- GitVerse CI for the **same reviewed source tree** is terminal success, observed through authenticated `git_provider_query ci_runs`.
- License and sensitive-file checks are completed; documented HACS exceptions remain visible rather than silently waived.
