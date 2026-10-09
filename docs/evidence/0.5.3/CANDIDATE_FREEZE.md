# 0.5.3 冻结候选 — 待现场验证

**FROZEN CANDIDATE / UNRELEASED / PENDING LIVE / PENDING HUMAN。**本页只冻结候选身份与离线证据；不含任何现场结果，不授权发布、合并、tag 或 Node 升级。现场执行步骤见[验证方案](../../plans/RC_0.5.3_VERIFICATION_PLAN.md)，准备过程见[准备记录](VERIFICATION_PREP.md)。

日期：2026-10-08（Asia/Shanghai）。分支 `codex/0.5.1`，冻结基线提交 `e024d12c8702ba1c659c2ec377715b1a91115998`。Node / Controller / embedded payload 均为 **0.5.3**，最低兼容 Node **0.3.1**，sing-box **1.13.18**。

## 固定输入

[188 个固定源码/测试/构建/CI 输入](SOURCE_INPUTS_FREEZE.json)，manifest SHA256：

```
da84b695ac19e91d1e9ebd67334a1be714440ab72a353d218e6a1a1ac775dbd7
```

输入规则与上一次收口一致（`tests/`、`lib/`、`scripts/`、`schemas/`、`bin/`、`.github/` 与指定的根文件，逐项按 LF 规范字节哈希）；与 [187 输入收口](SOURCE_INPUTS_CLOSEOUT.json)相比只多 `schemas/README.md`。生成器 `tmp/gen-source-inputs.py`（未提交的验证 helper）SHA256 记录在 manifest 的 `validation_helpers`。固定 `SOURCE_DATE_EPOCH=1791513039`。

## 制品

| 制品 | SHA256 |
| --- | --- |
| `dist/vincula-node-0.5.3.tar.gz` | `8abe989c125ba88caeeed6b929494e59f77caa3ef41f59710069ec7215ac049b` |
| `dist/vincula-controller-0.5.3.zip` | `65dbcc7b4ae19cfa480698ee2616ad67f43632460986ecae72ae89cfce0137a7` |
| `dist/vincula-controller-0.5.3/payload/payload-manifest.json` | `3389e3d6094082440cc036f7e355ba134160c061d7006c0d5c56d8e6be99f42f` |

sidecar `*.sha256` 的哈希同样记录在 manifest 的 `artifacts`。Node `release.lock` 与 Controller `controller.lock` 均由构建脚本重新生成并逐项校验。

## 离线门禁

| 检查 | 结果 |
| --- | --- |
| `tar -tzf` + Node sidecar + `release.lock` | PASS |
| Controller sidecar + `controller.lock` | PASS |
| 独立 ZIP 黑盒（无 repo `lib/`、`env -u PYTHONPATH`） | PASS；`bin/vcl-fleet version` → `vcl-fleet 0.5.3`，`controller.lock` 校验通过 |
| `scripts/check-controller-artifact.py` | `PASS OFFLINE`；schema 16、cache-only 入口 4；**`node_cli=NOT RUN`**（该段需要 root，本机非 root；CI 的 artifact job 以 `sudo -n` 跑同一脚本覆盖该段） |
| `bash tests/test-fleet.sh` | **All 1132 tests passed，exit 0** |
| `SQLITE_TMPDIR=<workspace>/tmp/sqlite-tmp bash tests/test.sh` | **All 1950 tests passed，exit 0** |
| Linux Python suite（非 root） | 155 项：153 PASS / 8 skip / 2 FAIL；两项失败是 `test_verify_extended` 既有的 root-only 用例（`Run this command as root`），CI 的 ubuntu job 用 `sudo -n` 跑同一命令 |
| Windows Python suite（本机 Python 3.12 复现） | 155 项：144 PASS / 11 platform skip，exit 0 |
| 远端 required CI | [run #100](https://github.com/Marz42/vcl/actions/runs/37874931681)（`e024d12`）七个 job 全绿：Ubuntu、Debian 12/13、Windows、concurrency、failure-injection、artifact |

原始日志（未提交的机器本地生成物）与哈希记录在 manifest 的 `logs`：`tmp/freeze-fleet.log`、`tmp/freeze-gate.log`、`tmp/freeze-unit.log`。

## 范围与下一步

- 本页冻结的候选已包含 FR-01（凭据引用隔离）、FR-02（有界审计同步，含评审补修）、FR-03/04（认证分类与安全摘要）及准备期 `workspace import` 暂存回落修复；各修复的自身绑定见 [FR-01](FR01_CREDENTIAL_ISOLATION.md)、[FR-02](FR02_BOUNDED_SYNC.md)、[FR-03/04](FR03_FR04_ERROR_MODEL.md)。
- **PENDING LIVE**：隔离 Controller 验证（基线、能力矩阵、observe 认证负例、大积压、限一页续传、`sync --full`、失败恢复）、七台混合 Fleet 复验、24h soak。
- **PENDING HUMAN**：H05 签署（[候选页](HUMAN_ACCEPTANCE.md)、[人工清单](../../plans/VCL_0.5-0.7_Human_Acceptance.md)），不代签。
- 已确定：阶段 A 在**全部七台**上轮换跑只读基线，并在**其中一台**上做大积压与限一页续传；执行细节与红线见[验证方案](../../plans/RC_0.5.3_VERIFICATION_PLAN.md)。
- 未执行：push / merge / tag / release / production apply / Node 升级。
