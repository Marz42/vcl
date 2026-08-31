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
| Date | 2026-08-31 |
| OS | Linux (WSL2 / CI ubuntu-latest matrix) |
| Commit | `6a4ee06` |

## Results

| Suite | Pass | Fail | Skip | Total |
| --- | --- | --- | --- | --- |
| tests/test.sh | 1819 | 0 | 0 | 1819 |

Gate: `All 1819 tests passed.` (includes `tests/test-fleet.sh` obs050 / mix050 / res050 / soak050 blocks).

## Schema contract tests

| Fixture | Expect | Result |
| --- | --- | --- |
| `tests/fixtures/schemas/capabilities/v1-valid.json` | PASS | **PASS** |
| `tests/fixtures/schemas/capabilities/v1-missing-schema.json` | FAIL | **PASS** |
| `tests/fixtures/schemas/capabilities/v1-unknown-capability.json` | PASS (unknown cap retained) | **PASS** |
| `tests/fixtures/schemas/telemetry/v1-valid.json` | PASS | **PASS** |
| `tests/fixtures/schemas/telemetry/v1-missing-node-id.json` | FAIL | **PASS** |

## 0.5.0 observation blocks (test-fleet.sh)

| Block | Coverage |
| --- | --- |
| `obs050` | capabilities/telemetry OK on 0.5.0; UNSUPPORTED on 0.3.x lax; upgrade plan allowlist |
| `obs-auth` | AUTH_FAILED on wrong observe key (no admin fallback) |
| oversize | `VCL_FAKE_CAP_OVERSIZE` / `VCL_FAKE_TEL_OVERSIZE` → Controller ERROR |
| telemetry audit | `VCL_FAKE_TELEMETRY_AUDIT=1` — config/users sha256 + systemd restart count stable |
| upgrade apply | happy path (`VCL_FAKE_UPGRADE=1`) identity → 0.5.0; migrate fail → journal FAILED |
| secret scan | journal / stdout no `vless://`, UUID markers, Reality key material |
| `mix050` | mixed 0.3.x + 0.5.0 fleet; lax UNSUPPORTED + probe not ERROR |
| `res050` | corrupt `operations.jsonl`; status/capabilities survive; module reload API intact |
| `soak050` | 1000× `fleet telemetry obsnode --json` — 0 failures |

## Failure injection

| Injection | Result |
| --- | --- |
| observe credential auth failure | AUTH_FAILED |
| oversize capabilities/telemetry | ERROR fail-closed |
| malformed JSON (`badjson` alias) | ERROR |
| upgrade migrate inject fail | apply exit ≠ 0; identity unchanged |
| corrupt operation journal | tolerant read; no panic |

## Concurrency

- 0.5.0 minimal; existing fleet concurrency tests unchanged (0.4.x suite retained).

## Secret scan

- **PASS:** obs050 upgrade journal, capabilities JSON, telemetry JSON — no key material in stdout captured by tests.

## UI boundary (G2)

- Existing B15 asserts: UI server loopback-gated; GET does not trigger telemetry SSH (D58 pattern retained).
