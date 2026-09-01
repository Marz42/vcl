# 0.5.0 — TESTS evidence

## Commands

```bash
bash tests/test.sh
bash scripts/build-release.sh
bash scripts/build-controller.sh
git diff --check
```

## Environment

| Field | Value |
| --- | --- |
| Date | 2026-09-01 |
| OS | Linux (WSL2 / CI ubuntu-latest matrix) |
| Commit | working tree on `release/0.5.0` (re-pin SHA after commit) |

## Results

| Suite | Pass | Fail | Skip | Total |
| --- | --- | --- | --- | --- |
| tests/test.sh | 1838 | 0 | 0 | 1838 |

Gate: `All 1838 tests passed.` (includes bounded SSH timeout, Infinity/NaN reject, upgrade ROLLED_BACK / PARTIAL recovery, SOURCE_DATE_EPOCH=0 ZIP clamp).

## Schema contract tests

| Fixture | Expect | Result |
| --- | --- | --- |
| `tests/fixtures/schemas/capabilities/v1-valid.json` | PASS | **PASS** |
| `tests/fixtures/schemas/capabilities/v1-missing-schema.json` | FAIL | **PASS** |
| `tests/fixtures/schemas/capabilities/v1-unknown-capability.json` | PASS (unknown cap retained) | **PASS** |
| `tests/fixtures/schemas/telemetry/v1-valid.json` | PASS | **PASS** |
| `tests/fixtures/schemas/telemetry/v1-missing-node-id.json` | FAIL | **PASS** |
| nested unknown / bad optionals / bad timestamps | FAIL | **PASS** |

## 0.5.0 observation blocks (test-fleet.sh)

| Block | Coverage |
| --- | --- |
| `obs050` | capabilities/telemetry OK on 0.5.0; UNSUPPORTED on 0.3.x lax; upgrade plan allowlist |
| `obs-auth` | AUTH_FAILED on wrong observe key (no admin fallback); exit 1 for capabilities + telemetry |
| oversize | padded raw + raw 1 MiB oversize → Controller ERROR before `json.loads` |
| telemetry audit | `VCL_FAKE_TELEMETRY_AUDIT=1` — config/users sha256 + systemd restart count stable |
| upgrade apply | happy path; migrate fail; SKIPPED already-current; admin-only (observe AUTH ignored); post-check PARTIAL; identity drift PARTIAL; plan REFUSED exit 1 |
| secret scan | journal / stdout no `vless://`, UUID markers, Reality key material |
| `mix050` | mixed 0.3.x + 0.5.0 fleet; lax UNSUPPORTED + probe not ERROR |
| `res050` | corrupt `operations.jsonl`; status/capabilities survive; module reload API intact |
| `soak050` | 1000× `fleet telemetry obsnode --json` — 0 failures (**offline fixture only**; no live state-growth) |

## Failure injection

| Injection | Result |
| --- | --- |
| observe credential auth failure | AUTH_FAILED, exit 1 |
| oversize capabilities/telemetry | ERROR fail-closed |
| malformed JSON (`badjson` alias) | ERROR |
| upgrade migrate inject fail | apply exit ≠ 0; identity unchanged |
| upgrade post-check / identity drift | restore attempt → **ROLLED_BACK** or **PARTIAL** + recovery |
| upgrade plan off-allowlist | REFUSED, exit 1 |
| Infinity / NaN in observation JSON | ERROR / schema reject |
| bounded SSH hang / flood | TimeoutExpired within ~timeout |
| SOURCE_DATE_EPOCH=0 controller zip | builds (ZIP epoch clamped ≥ 1980) |
| corrupt operation journal | tolerant read; no panic |

## Concurrency

- 0.5.0 minimal; existing fleet concurrency tests unchanged (0.4.x suite retained).

## Secret scan

- **PASS:** obs050 upgrade journal, capabilities JSON, telemetry JSON — no key material in stdout captured by tests.

## UI boundary (G2)

- Existing B15 asserts: UI server loopback-gated; GET does not trigger telemetry SSH (D58 pattern retained).
