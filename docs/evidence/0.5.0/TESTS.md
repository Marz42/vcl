# 0.5.0 — TESTS evidence

> G0 template. Fill after G1 Offline Gate.

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
| Date | _TBD_ |
| OS | _TBD_ |
| Commit | _TBD_ |

## Results

| Suite | Pass | Fail | Skip | Total |
| --- | --- | --- | --- | --- |
| tests/test.sh | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Schema contract tests (planned G1)

| Fixture | Expect |
| --- | --- |
| `tests/fixtures/schemas/capabilities/v1-valid.json` | PASS |
| `tests/fixtures/schemas/capabilities/v1-missing-schema.json` | FAIL |
| `tests/fixtures/schemas/capabilities/v1-unknown-capability.json` | PASS (unknown cap retained) |
| `tests/fixtures/schemas/telemetry/v1-valid.json` | PASS |
| `tests/fixtures/schemas/telemetry/v1-missing-node-id.json` | FAIL |

## Failure injection (planned)

- SSH timeout on `capabilities` / `telemetry`
- malformed JSON
- oversize response
- observe credential auth failure
- upgrade: migrate inject fail mid-apply; rollback restores LKG

## Concurrency

- _TBD_ (0.5.0 minimal; expanded in 0.5.1 monitor)

## Secret scan

- _TBD_
