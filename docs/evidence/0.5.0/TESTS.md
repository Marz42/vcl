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
| Date | 2026-09-25 |
| OS | Debian (WSL2; clean `git archive` of the code commit) |
| Commit | `98423ed` |

## Results

| Suite | Pass | Fail | Skip | Total |
| --- | --- | --- | --- | --- |
| tests/test.sh | 1863 | 0 | 0 | 1863 |

Gate: `All 1863 tests passed.` (includes bounded SSH timeout, Infinity/NaN reject, upgrade ROLLED_BACK / PARTIAL recovery, SOURCE_DATE_EPOCH=0 ZIP clamp, canonical tar modes, and per-node clock measurement). Node and Controller builds passed with `SOURCE_DATE_EPOCH=1790260874`; candidate SHAs are recorded in [`SUMMARY.md`](SUMMARY.md). `git diff --check` passed.

The cross-filesystem mismatch was caused by DrvFs reporting all staged files as mode `0777`; the Node tar preserved those modes and changed the embedded payload in the Controller zip. `build-release.sh` now stages canonical modes in POSIX `/tmp` before archiving.
Clock skew comparison now uses the midpoint of each identity SSH call. The fixture confirms a 56-second delay before the call no longer becomes a false WARN, while genuine 45-second and 400-second skew retain WARN and FAIL behavior.

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
| `obs050` | capabilities/telemetry OK on 0.5.0; UNSUPPORTED on 0.3.x lax; upgrade plan allowlist; registry/remote/snapshot `node_id` and `instance_id` mismatch rejected |
| `obs-auth` | AUTH_FAILED on wrong observe key (no admin fallback); exit 1 for capabilities, telemetry, probe, verify; identity/status/verify remote reads all use observe |
| oversize | padded raw + raw 1 MiB oversize → Controller ERROR before `json.loads` |
| telemetry audit | `VCL_FAKE_TELEMETRY_AUDIT=1` — config/users sha256 + systemd restart count stable |
| upgrade apply | happy path; migrate fail; SKIPPED already-current; admin-only (observe AUTH ignored); post-check PARTIAL; identity drift PARTIAL; plan REFUSED exit 1 |
| secret scan | journal / stdout no `vless://`, UUID markers, Reality key material |
| `mix050` | mixed 0.3.x + 0.5.0 fleet; lax UNSUPPORTED + probe not ERROR |
| `res050` | corrupt `operations.jsonl`; status/capabilities survive; module reload API intact |
| `soak050` | 1000× `fleet telemetry obsnode --json` — 0 failures (**offline fixture**) |
| Live soak | `scripts/soak-0.5.0-telemetry.sh` — 2026-09-07 historical metrics OK; RSS/FD gate **PENDING** re-run ([`SOAK.md`](SOAK.md)) |

## Failure injection

| Injection | Result |
| --- | --- |
| observe credential auth failure | AUTH_FAILED, exit 1 |
| wrong telemetry node_id / instance_id | ERROR, no snapshot accepted |
| oversize capabilities/telemetry | ERROR fail-closed |
| malformed JSON (`badjson` alias) | ERROR |
| upgrade migrate inject fail | apply exit ≠ 0; identity unchanged |
| upgrade post-check / identity drift | in-place `upgrade rollback` → **ROLLED_BACK** or **PARTIAL** + recovery |
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
