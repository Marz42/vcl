# 0.5.5 candidate identity

**FROZEN CANDIDATE / CI PASS / UNRELEASED / DEFERRED LIVE / PENDING HUMAN.**
This records one candidate; it is not a release, H05 signature or main merge.
The user deferred field work on 2026-11-03 because the Controller/Workspace is
currently unavailable. [Resume checklist](LIVE_FOLLOWUP.md).

| Input | Fixed value |
| --- | --- |
| Approved baseline | `08af38324fbbcbe75b13c0bc026ee1ce234e8449` |
| Source/validation commit | `653f7ddb28b8ff4ea199dce6c4187842cca9190e` |
| Last runtime change | `7bef780011b2e53db1989e6fb1db17b0173be53c`; the later commit changes only CI/test isolation |
| Node / Controller / embedded payload | 0.5.5 / 0.5.5 / 0.5.5 |
| Minimum compatible Node | 0.3.1; real prerelease origins are not rewritten |
| Accounting / Fleet-cache schema | 5 / 5 |
| Fixed build epoch | `SOURCE_DATE_EPOCH=1793689859`, from the last runtime commit |
| Fixed input set | [201 source/test/build/CI files](SOURCE_INPUTS.json), LF-normalized; final manifest digest recorded below |
| Archive membership | [PAYLOAD_MEMBERS.json](PAYLOAD_MEMBERS.json), 24 Node and 63 Controller file members |
| Embedded payload manifest | [PAYLOAD_MANIFEST.json](PAYLOAD_MANIFEST.json) |

SOURCE_INPUTS SHA256: `5e55b6c1d115db842a4b07209f2fd99e86535535c7ca410162d9eacfc98cd3a3`.

| Local archive | SHA256 |
| --- | --- |
| `dist/vincula-node-0.5.5.tar.gz` | `383362401f0574c44649e5071b81f31ab03f03f54588ee6456e62e4627524671` |
| `dist/vincula-controller-0.5.5.zip` | `14312b21216bb4863a68c50ad9a443ac44786052c04b7648811cf4ca21ec233b` |

Use these digests for the candidate. CI builds from its own merge ref/epoch have
their own artifact identity and are not substituted for this fixed pair. A
second fixed-epoch build of the runtime inputs produced byte-identical Node and
Controller archives, including a rebuild under `653f7dd`. The seven required jobs
passed in [CI #129](https://github.com/Marz42/vcl/actions/runs/41595858638),
recorded in [REMOTE_CI_CODE](REMOTE_CI_CODE.json). CI/test-only source changes
must still pass the seven jobs;
they do not silently change the frozen installation bytes.

To reproduce, use a POSIX LF checkout of the fixed source commit and run:

```bash
export SOURCE_DATE_EPOCH=1793689859 PYTHONDONTWRITEBYTECODE=1
bash scripts/build-release.sh
bash scripts/build-controller.sh
python3 -B scripts/check-controller-artifact.py dist/vincula-controller-0.5.5.zip
```

Build scripts regenerate and verify the runtime locks. The complete archive
membership includes the distributed history-coverage schema/fixtures; Controller
also ships cache-status fixtures. The outer archive/payload SHA covers those
contract assets, in addition to the runtime locks. Do not edit `dist/` manually.

Local/remote test details and retained failures: [VERIFICATION](VERIFICATION.md).
Current gate states: [SUMMARY](SUMMARY.md). Historical evidence applicability:
[A/B/C impact](HISTORICAL_EVIDENCE_IMPACT.md). Migration/capacity/private-input
instructions: [runbook](../../operations/0.5.5-closeout-runbook.md).

Field gates remain deferred: seven real mixed-version nodes, recoverable canary,
two-source upgrade/rollback and <=3s measurement, actual credential/observer/
accountd permissions, real proxy/Inspect/Drift and new continuous >=24h RC soak.
Whole-connection approximate bytes belong to the UTC start day; unverified legacy
history is separate and previously deleted history is not recovered. No automatic
history deletion or 0.6.x implementation is included.

H05-01..08 must be explicitly signed PASS before PR #13 is undrafted and merged
using a merge commit. Tags and external release remain outside this action.
Any runtime change after this candidate requires a new fixed identity and review
of the affected checks and field evidence.
