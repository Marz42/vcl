# 0.5.5 verification record

Runtime code source: `7bef780011b2e53db1989e6fb1db17b0173be53c`, following the approved
`08af383` baseline. Node and Controller both stamp 0.5.5. This record separates
code/local/remote/synthetic/field/human proof. Field execution was deferred by
the user on 2026-11-03; H05 is unsigned and main is unchanged.

The final validation-input commit is `653f7ddb28b8ff4ea199dce6c4187842cca9190e`.
Its only changes from the runtime commit are `.github/workflows/ci.yml` and
`tests/test.sh`: inherited bytecode suppression for privileged child interpreters
and in-memory syntax compilation. Runtime/build/package members remain identical.

| Check | Result and boundary |
| --- | --- |
| Windows Python 3.11 | PASS: 196 discovered, 183 executed, 13 Linux-specific skips; `windows-restore-final.log` |
| Debian WSL, Python 3.13.5, root | PASS: 196 executed, zero skips. Includes actual temporary-filesystem/UID/GID permission tests; `qualified-7bef780/linux-qualified.log` |
| Ordinary Linux user, root-owned source bytecode directory | PASS: Python 196 discovered, 186 executed, 10 required-permission skips; Bash 1,968 assertions, zero `not ok`, exit 0 |
| Bash/Fleet complete gate, root Linux | PASS: 1,966 assertions, zero `not ok`, exit 0 |
| Node/Controller package build, locks and sidecars | PASS; fixed epoch 1793689859 |
| Isolated artifact checker | PASS OFFLINE: 18 schemas, five cache-only surfaces, fixture Node CLI PASS; separate from real proxy/Node acceptance |
| Deterministic rebuild at frozen epoch | PASS: byte-identical Node/Controller archives, including the rebuild under final validation commit `653f7dd` |
| Seven required remote jobs | PASS [CI #129](https://github.com/Marz42/vcl/actions/runs/41595858638), all seven successful; actual Python 3.10 and mandatory root permission checks run in Ubuntu |
| Ten synthetic nodes, actual two hours | PASS OFFLINE: 7,200.016 seconds, 2,400 samples, concurrency <=8, zero observation errors; 17 input hashes exactly match the candidate |
| Seven real nodes, canary, two-source upgrade/rollback, real proxy, permissions, Inspect/Drift, new continuous 24h | DEFERRED USER / NOT RUN |
| Human H05-01..08 | PENDING HUMAN / NOT SIGNED |

The Windows suite uses workspace-local temporary paths and loopback-only test
servers. Local sandbox TEMP replacement/socket restrictions were rechecked with
workspace TEMP and authorized local test execution. Platform skips are not
substitutes for Linux privilege checks: root Linux and remote root jobs execute
those checks. Docker is unavailable locally; actual Python 3.10 execution belongs
to the remote Ubuntu job, using a read-only source mount and network disabled
during tests.

Regression scope includes immutable selector collision/isolation/publication and
explicit legacy migration, observe state after replace, secret-free child argv
and private restore input, UTC/day/window precision, independent retention and
transactional contribution replay, unknown-tag liveness, staged/concurrent/
interrupted schema migration, legacy-only Fleet totals, backup required members
and unreadable components, capacity/low-disk/lock/page rollback, initial schema
creation and batch SQL atomicity, CLI no-create reads and artifact contracts.
Mock SSH, simulated telemetry and temporary service fixtures remain offline
evidence, even where historical test labels contain `LIVE`.

Earlier failures remain in [FAILURE_LOG_INDEX.json](FAILURE_LOG_INDEX.json).
The failed files are machine-local and their hashes/labels are retained:

- Initial Bash passes of implementation exposed old version/schema and
  raw-rebuild fixture assumptions, plus integration differences; the separate
  retained runs had 65, 24, 13, 3 and 1 failed assertions. The final single
  instance-history assertion was restored to the existing seconds format:
  the six-digit contract applies to connection timestamps and audit bounds.
- [CI #124](https://github.com/Marz42/vcl/actions/runs/41591356442), `025f7b3`,
  failed two Python 3.10 corrupt-DB classifications because that runtime lacks
  the newer exception code attributes. `dafc81a` adds the bounded classification
  fallback; do not rewrite #124 as green.
- [CI #125](https://github.com/Marz42/vcl/actions/runs/41591892737), `dafc81a`,
  and its independent local Bash run failed the old v3 minimal-schema coverage
  case. `c86376f` handles the absent optional close column; the complete later
  Bash run passed 1,966 assertions. The preceding assertion was not removed.
- Subsequent fixes add initial/batch capacity rollback (`5de79f5`) and shared
  backup encoding/JSON-root admission (`7bef780`), with dedicated regressions.
  New runs supersede those inputs only for their changed code, not their raw
  historical outcomes.
- [CI #128](https://github.com/Marz42/vcl/actions/runs/41594631099), `7bef780`,
  failed four Ubuntu syntax checks after root child interpreters created a
  root-owned source `__pycache__`. This is a test-isolation failure; Debian 12/13,
  Python contracts and the packages passed. `653f7dd` prevents inherited import
  writes and compiles the same source in memory; the explicit py_compile baseline
  still writes only inside its disposable fixture. The failed log is retained.

The exact frozen inputs, final test-log digests and artifact identity are in
[SOURCE_INPUTS](SOURCE_INPUTS.json) and [candidate freeze](CANDIDATE_FREEZE.md).
Earlier [A/B/C evidence](HISTORICAL_EVIDENCE_IMPACT.md) remains supplementary.
The code CI snapshot is [REMOTE_CI_CODE](REMOTE_CI_CODE.json); the synthetic raw
summary, database/report digests and reuse boundary are retained in
[SIMULATED_MATRIX_2H](SIMULATED_MATRIX_2H.json). Maximum sample gap was 33.046s,
within its 76s ceiling; observation DB was 5,423,104 bytes. This does not close
the seven-real-node, real proxy/Inspect or 24h field dimensions.
An independent read-only DB check reconciled 2,400 raw samples and 2,400 rollup
samples, with 237..241 samples per node (scheduler jitter). The committed sample
window was `2026-11-03T05:31:51.517401Z`..`2026-11-03T07:31:47.045230Z`;
the separate monotonic run duration was 7,200.016s.
