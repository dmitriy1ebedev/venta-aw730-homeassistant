# Venta AW730: Tuya LAN and MQTT transport decision notebook

Status: V200-01, research-only draft, 2026-11-23. No real-device transport switch, new Tuya session, key retrieval, MQTT configuration change, or Home Assistant deployment has been performed.

## Confirmed baseline and limits

- The project compatibility record documents one AW730 operating through the tested LocalTuya fork with Tuya LAN 3.4. This is evidence for that installation, not support for other AW7xx models or firmware.
- H96 read-only Docker status on 2026-11-23: Mosquitto running/healthy; Zigbee2MQTT running/healthy. Existing MQTT infrastructure can be reused in a future design, but its presence does not make AW730 a native MQTT device.
- H96 Home Assistant reports healthy and its installed Venta component manifest is 1.2.0 (operational canary). The owner reports no observable loss of existing functionality. This is not a published immutable release or authorization to migrate the existing YAML or HomeKit pairing.
- Real AW730 simultaneous-connection limit, local-key rotation behavior, retained DP update cadence, and production command-to-confirmation latency are NOT measured. Do not assume facts from other Tuya devices apply to this unit.

## Alternatives (A/B/C/D)

| Option | Device writer | Transport path | Main benefit | Main costs/risks | Initial decision |
| --- | --- | --- | --- | --- | --- |
| A: keep LocalTuya, no new MQTT path | Existing LocalTuya only | AW730 -> LocalTuya -> HA -> HomeKit/Alice | No extra process or compatibility migration | Existing LocalTuya dependency remains | Baseline, preferred until a defect or measured performance bottleneck |
| B: keep LocalTuya; optional read-only MQTT fanout | Existing LocalTuya only | AW730 -> LocalTuya -> HA state -> MQTT subscribers | Reuses healthy broker for other consumers | Extra publication/serialization/ACL, stale data, loop risk | Candidate for observability only; do not create second HA device or command route |
| C: Go Tuya LAN client with optional MQTT output | Go client ONLY after controlled cutover | AW730 -> Go -> MQTT -> HA | Independent transport and external subscribers | New key custody, state translation, reconnect, MQTT lifecycle, pairing/identity migration | Research/simulation only until explicit canary |
| D: Go Tuya LAN direct HA adapter | Go client ONLY after controlled cutover | AW730 -> Go -> HA -> HomeKit/Alice | Avoids MQTT hop if only HA consumes data | Requires an HA integration/service boundary and same migration protections | Benchmark against C; do not assume Go is inherently faster end-to-end |

B is not a replacement for LocalTuya. C and D require deactivating the old LAN writer before any live connection. MQTT Cloud Client ID/Secret and Tuya local_key have distinct purposes: possessing cloud identifiers does not expose an MQTT endpoint on AW730.

## Libraries for a future Go-only prototype

- cB-Sigma/tuyalan: Go module; published v0.3.0 (2026-10-11) under Apache-2.0. Documentation describes Tuya LAN 3.1-3.5, 3.4 session-key negotiation and a separate simulated-device repository. Pre-1.0 API is not a stable contract. No AW730-specific compatibility has been demonstrated.
- MXVXID/tiny-go: MIT-tagged Go port of tinytuya, with documentation claiming Tuya LAN 3.1-3.5 and Go 1.26+ for its published version. Verify upstream attribution, test coverage, and package source before selecting a dependency; its README claims are not evidence of AW730 functionality.
- make-all/tuya-local: Python Home Assistant alternative that handles local Tuya firmware with device profiles. It is an option for comparison, NOT a drop-in replacement for the existing validated LocalTuya entity IDs or HomeKit integration.
- Eclipse Paho paho.golang/autopaho: existing Go MQTT v5 client with automatic reconnect. Use only if an MQTT adapter is justified; do not couple Tuya frame handling to MQTT delivery semantics.

All candidate dependencies need a locked version, license and security review, API tests, and synthetic frame validation before being adopted.

## Threat model and invariants

1. Real local_key, Device ID, Tuya cloud credentials, HomeKit keys, pairing materials, private network identifiers, and raw config entries never enter Git, CI artifacts, debug logs or public bug reports.
2. Exactly one active Tuya LAN controlling session for AW730 during a live migration. No parallel trial connection, polling client, brute-force scan or unsolicited DP command against the physical device.
3. MQTT uses a separate minimal-privilege account and scoped publish/subscribe ACLs if activated; do not reuse Zigbee2MQTT credentials. Commands must not be retained. Avoid message loops between HA and broker.
4. MQTT Discovery uses stable unique IDs and re-announces discovery after the Home Assistant birth message; use availability/LWT and explicit state reconciliation. Retained discovery/state can be appropriate for known-safe values, but stale retained topics and duplicate HA devices are failure modes.
5. Preserve the original HomeKit bridge/AID/IID, config and entity IDs, and Alice export membership. Migration is dry-run first, owner-approved canary second, with backup and rollback.

## Reproducible evidence plan (no device actuation by default)

Phase 1 - read-only baseline: inventory versions, Mosquitto and Zigbee2MQTT health, existing HA event chronology and availability errors. Capture sanitized event timestamps and resource counters only. A single Docker resource snapshot is not a performance benchmark; HA CPU cannot be attributed to LocalTuya without instrumentation.

Phase 2 - isolated benchmark: loopback fake Tuya LAN 3.4 device, dedicated disposable MQTT broker and HA fixture. Use deterministic DP mappings for power, Auto/Manual/Sleep, five fan speeds, humidity 30-70%, LED and sensor feedback. Test wrong key, missing DP, half-open session, reconnect, duplicate command IDs, delayed state push, retained command rejection, availability, LWT and discovery collision. No real hardware.

Phase 3 - native Go verification: gofmt, go vet, go test ./..., go test -race ./..., go test -bench=. -benchmem ./...; run through the authorized MCPshka runner/CI profile rather than an unmanaged heavy shell on H96. Python tests remain for the Python HA integration and JavaScript tests remain for the UI. Compare allocations, throughput, goroutine count and CPU/RAM in repeatable profiles.

Phase 4 - evidence comparison: for the same actions and simulated load compare command -> acknowledged state and reconnect latency p50/p95, stale/duplicate event rate, CPU, RAM, process count and maintenance complexity. Live command latency testing requires a separately approved physical-device test; until then report only synthetic numbers and passive observations.

Decision: choose A unless B has a real additional subscriber use case or C/D can prove a worthwhile reduction in failures/latency/maintenance cost while preserving identity and rollback. Do not claim that replacing Python LocalTuya with Go or adding MQTT improves performance without measurements.

## Evidence and remaining V200-01 work

Observed: running/healthy H96 Mosquitto and Zigbee2MQTT containers; verified installed Venta 1.2.0 manifest; project compatibility report for one AW730 Tuya LAN 3.4 system. Public sources below were reviewed 2026-11-23. Still missing: verified real-device concurrent-connection behavior, safe local-key rotation behavior, normalized baseline p50/p95 and reconnect failure rate, source-review of candidate Go modules, broker ACL topology, and an explicit go/no-go decision. Therefore V200-01 remains OPEN.

Sources:
- https://www.home-assistant.io/integrations/mqtt/
- https://developer.tuya.com/en/docs/iot-device-dev/TuyaOS-iot_abi_device_active_lan?id=Kcogfpv7g7eb9
- https://pkg.go.dev/github.com/cB-Sigma/tuyalan
- https://pkg.go.dev/github.com/MXVXID/tiny-go
- https://github.com/make-all/tuya-local
- https://github.com/eclipse-paho/paho.golang
- docs/compatibility.md (project installation evidence)
- ROADMAP.md (scope, order, and exit criteria)
