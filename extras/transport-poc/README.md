# Offline transport contract (V200-02/03)

This Go standard-library-only prototype has no executable, network transport,
credential storage or HA imports. It is an offline simulation of a DP adapter and migration
contract, not an implementation of Tuya LAN cryptography or a replacement for
LocalTuya. Only the fixed public synthetic fixture is accepted for migration.
Unknown write outcomes require a fresh snapshot; command IDs are never replayed
inside one adapter lifetime. Real persistent idempotency and session handling
would require independent design and tests before any deployment.

Run in CI with Go 1.22 or newer:
```sh
GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off go test -race -count=1 ./...
GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off go test -run '^$' -bench . -benchmem -benchtime=100ms ./...
```
Benchmarks measure in-memory operations only. No LAN/device/HA latency may be
inferred from them. See [transport research](../../docs/TRANSPORT_RESEARCH.md).
