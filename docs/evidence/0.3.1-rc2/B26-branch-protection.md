# B26 — GitHub branch protection (main)

**Result: PASS** (2026-08-20)

Configured via GitHub API (`gh api …/branches/main/protection`):

| Setting | Value |
| --- | --- |
| Require pull request | yes (`required_approving_review_count`: 0) |
| Require status checks | yes |
| Require branch up to date | yes (`strict`: true) |
| Required checks | `unit (ubuntu-latest)`, `unit (debian:12)`, `unit (debian:13)`, `concurrency`, `failure-injection`, `artifact` |
| Allow force pushes | **false** |
| Allow deletions | **false** |
| Enforce admins | **true** |

P1-05 **CLOSED**.
