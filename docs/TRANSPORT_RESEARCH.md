# Venta AW730: transport research and economic decision (V200-01)

Reviewed 2026-11-26 against the pinned public sources below and the project's
existing compatibility evidence. This is a transport study, not approval to
connect to hardware, retrieve keys, change a broker, or migrate HA.

## Evidence and comparison

The existing AW730 Smart Life variant has operated with LocalTuya 2026.10.0,
Tuya LAN 3.4. Exact physical firmware, parallel connection limit, real command
latency, reconnect failure rate, CPU/RAM and key-rotation behavior are not
measured. The earlier project observations of healthy HA/Mosquitto/Zigbee2MQTT
are operational observations, not transport benchmarks.

| Alternative | Protocol and license evidence | Integration / maintenance cost | Decision |
|---|---|---|---|
| Existing xZetsubou LocalTuya | pinned 2026.10.0 const.py lists 3.1–3.5; GPL-3.0 repository | Already retains HA entity IDs, template, HomeKit bridge and Alice path; ongoing HA compatibility testing | Retain |
| make-all/tuya-local | MIT repository, README lists 3.1–3.5 and device variants | Different profile/config integration; no verified drop-in AW730 identity migration | Do not replace solely for a different implementation |
| Own Go client using cB-Sigma/tuyalan v0.3.0 | Apache-2.0; Go 1.22, upstream claims 3.4/3.5 authenticated sessions and independent frame tests | New protocol/session/reconnect maintenance, key custody, HA adapter and release/rollback work | Simulation only; no dependency adopted |
| Own Go client with tiny-go | Cached pkg.go.dev listing exists; upstream repository returned 404 on review | Source/license maintenance cannot be independently confirmed now | Exclude from candidate dependency selection |
| Optional MQTT fanout | HA MQTT documentation supports state, availability and discovery | Extra ACLs, broker and stale/retained message risks; no second writer | Only if an actual additional subscriber needs it |

TinyTuya (MIT) documents LAN 3.1–3.5; 3.4 and 3.5 use different authenticated
framing and per-session key negotiation. This is a community protocol
reference, not manufacturer certification for Venta. The TuyaOS vendor
documentation describes LAN binding/control as separate from cloud
activation. The LocalTuya guide advises closing Smart Life/Tuya Smart and
avoiding multiple local integrations because some devices permit one local
connection. tuya-local documents the same practical limitation and warns
that re-pairing changes the local key. The actual AW730 session limit and
rotation behavior remain unverified; do not deliberately re-pair to test it.

License assessment: GPL-3.0 obligations must be evaluated before distributing
a derivative of LocalTuya; do not copy its code into the MIT project.
MIT/Apache-2.0 dependencies require attribution/license preservation and
applicable notices. No upstream implementation is bundled or copied in this
prototype; the Go module uses only the standard library. Verify exact
license text, attribution, transitive dependencies and security review
before selecting any real client library. Existing template attribution
remains unchanged.

## Threats and operating constraints

- Device credentials remain in authorized private configuration. Key rotation
  is an authentication/reconciliation event: stop writes, obtain the updated
  key through the supported owner-authorized process, reconnect and read state.
  Never log keys, brute-force, or automatically re-pair.
- One active controller of a physical AW730; never test a second LAN client
  in parallel. Session generation, bounded retry, full-state reconciliation
  and no replay of unknown writes are required. A successful write dispatch
  is not evidence of state change.
- Strict known DP types/values, safe invalid/missing status handling and no
  unverified reset writes. Reject obsolete session responses and malformed
  data. Avoid new remote services or unnecessary cloud credentials.
- MQTT, if justified later, needs scoped credentials, authenticated access,
  availability and stale-state handling; never retain command messages,
  duplicate the HA device or feed a command loop.
- Preserve current config entries, entity IDs, HomeKit bridge/AID/IID, pairing
  and Alice exports; test reversible migration on synthetic fixtures first.
  No live action without separate explicit permission.

## Economic evaluation

Keeping LocalTuya adds zero new processes or credential stores. A replacement
adds a session client, HA integration boundary and independent maintenance
and migration burden; an MQTT path adds another delivery/security boundary.
Existing functioning controls provide a concrete baseline; no demonstrated
reduction in hardware errors, latency, maintenance or resource cost offsets
the added engineering and pairing risks. No monetary savings estimate is
claimed. Decision: **NO-GO for production replacement**; retain LocalTuya.
A simulated contract is worthwhile solely to validate safe state transitions
and rollback. Revisit only after a reproducible, separately approved,
single-writer device comparison with measured p50/p95 confirmation/reconnect
latency, error rate, CPU/RAM and preserved identities. No release 2.0 merely
to satisfy a version number.

## Measured evidence and decision boundary (V200-04)

GitHub Actions run 45767945176, job 139733316459, Go 1.26.11 linux/amd64:
253 Python tests, eight Go tests and five injected-fault subtests passed;
Go vet and race checks passed. The original in-memory readback benchmark
measured 69,072 operations at 1,657 ns/op (1,614 B/op, 15 allocations/op),
and reconnect 190,044 operations at 581.2 ns/op (672 B/op, 4 allocations/op).
This measures the initial simulation before the additional state-projection
check, not real LAN transport. Reproduction commands are in the prototype README.

| Comparison dimension | Existing LocalTuya | Go simulation | Evidence-based conclusion |
|---|---|---|---|
| Stability | Previously observed working AW730; current physical error rate unknown | Five injected write faults, reconnect and stale-writer tests | No comparative hardware reliability benefit established |
| Command latency | Real confirmation p50/p95 not measured | In-memory ns/op only | Not comparable to LAN latency; no speedup claim |
| Maintenance | Existing tested HA integrations and release checks | Adds a real client, authentication, migration and HA adapter if deployed | Additional maintenance burden, no proven savings |
| Locality | Existing local Tuya LAN path | No network at all; not a functional LAN client | No demonstrated locality gain |
| Update and identity risk | Existing compatibility history, entity IDs and pairing | Synthetic migration projection and rollback preserve fixture identities only | No proven production migration or pairing equivalence |

**Final decision: NO-GO for 2.0 production transport.** Keep LocalTuya; no
new network connection, credential store, MQTT route or 2.0 release. The
simulator and synthetic migration contract are research deliverables, not
an installable alternative. Any future reconsideration needs comparable
measurements on an approved single-writer real device and a separately
approved migration rehearsal. No missing measurement is substituted by a
simulation result.

## Reproducible research sources

- LocalTuya 2026.10.0, protocol list:
  https://github.com/xZetsubou/hass-localtuya/blob/7f3be1999f581863ffa984e86ed359857f8bcab1/custom_components/localtuya/const.py
- LocalTuya connection guidance:
  https://github.com/xZetsubou/hass-localtuya/blob/7f3be1999f581863ffa984e86ed359857f8bcab1/documentation/docs/usage/configure_add_device.md
- tuya-local pinned README and license:
  https://github.com/make-all/tuya-local/blob/e9064cf33d6c1138718b159770b386409a46dc8f/README.md
- TinyTuya pinned protocol reference:
  https://github.com/jasonacox/tinytuya/blob/b0482da13af473677a78ea76a94bd8ed2c37a3e7/PROTOCOL.md
- tuyalan v0.3.0 README, Go module and license metadata:
  https://github.com/cB-Sigma/tuyalan/tree/98aa6ce4eba103f55175a6d2b4ebfb20fa46798d
- https://pkg.go.dev/github.com/cB-Sigma/tuyalan
- https://pkg.go.dev/github.com/MXVXID/tiny-go/tuya
- https://developer.tuya.com/en/docs/iot-device-dev/TuyaOS-iot_abi_device_active_lan?id=Kcogfpv7g7eb9
- https://www.home-assistant.io/integrations/mqtt/
- [Existing project compatibility](compatibility.md)
- [Offline Go simulation](../extras/transport-poc/README.md)

## По-русски

Штатный LocalTuya остаётся рабочим транспортом. Публичные исходники
подтверждают различия протоколов, возможность смены ключа при повторном
сопряжении и ограничение числа локальных подключений у части устройств.
Это не измерения AW730. Исследовательский Go-адаптер не открывает сокеты и не
хранит ключи. Переход на него экономически не обоснован: выгода не доказана,
а дополнительные расходы на сопровождение и риски миграции известны.
