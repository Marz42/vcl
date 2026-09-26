# 0.5.1 本地测试记录

日期：2026-09-27。状态：**PASS LOCAL**，真实VPS/远端CI不在本轮执行范围。测试源码/制品由[ARTIFACTS](ARTIFACTS.md)的100项输入清单绑定，已逐项核对与最终工作树的Git规范化内容一致。

## 环境与命令

- Windows PowerShell：Python 3.12.14，运行新增stdlib unittest；Node运行`--check`验证静态JS语法。
- Debian 13.3 WSL2，Python 3.13.5，x86_64，普通UID 1000：项目副本位于POSIX `/tmp`，文本规范化为Git提交使用的LF，shell/fixture设置可执行位；不直接在Windows CRLF工作树执行Bash。
- Debian WSL2，root：仅运行专用权限测试，所有变更限于TemporaryDirectory和本机Unix socket；没有创建系统用户、修改`/etc`、安装unit或启动服务。

```bash
python3 tests/test_monitor.py
python3 tests/test_accountd_runtime.py
python3 tests/test_observer.py
python3 tests/test_monitor_schema.py
bash tests/test.sh
bash scripts/build-release.sh
bash scripts/build-controller.sh
sudo -n python3 tests/test_accountd_privileges.py
systemd-analyze verify dist/vincula-node-0.5.1/lib/vincula-accountd.service \
  dist/vincula-node-0.5.1/lib/vincula-observer.socket \
  dist/vincula-node-0.5.1/lib/vincula-observer@.service
git diff --check
```

`tests/test.sh`已source Fleet suite；新增Python suites在其中各计为一个顶层断言，不把子测试数量重复加到顶层总数。`SOURCE_DATE_EPOCH=1790386657`固定构建输入。

## 结果

| 检查 | 实际结果 |
| --- | --- |
| 最终全量Bash / Fleet suite | **1868 assertions PASS，0 fail**；`All 1868 tests passed.` |
| Linux新增Python suites | 37 tests PASS，0 fail，0 skip（monitor 24 / accountd runtime 5 / observer 6 / schema 2） |
| Windows新增Python suites | 36 PASS，0 fail，1平台skip：SO_PEERCRED；该项在Linux实际通过 |
| Linux真实UID/GID权限测试 | 5 PASS，0 fail/skip |
| JS syntax | PASS：`node --check lib/vincula-ui/static/app.js` |
| Node/Controller制品与lock/digest | **PASS**：sidecars、包内lock、嵌入Node payload、16项Node文件、unit模式0644 |
| systemd unit静态验证 | **PASS**：对最终打包后的三个unit验证，exit 0，无诊断；不等于服务实测 |
| git diff --check | **PASS**；Windows工作树的LF/CRLF提示不影响Git规范化内容校验 |

本地原始全量日志保留于仓库`tmp/051-final-tests.log`（忽略、不入Git），SHA-256：`32af7a67fe12fe5338e2307ab95d33c678a3f7c36201b9f3ee2a353948f5f40d`。单元/fixture通过不能替代`VCL_INTEGRATION=1`真实联网模式；本轮未启用该模式。最终源副本为本机`/tmp/vcl-051-final.wsHgQFge`，不将该临时位置当可移植制品地址。

## 有效覆盖与边界

- 12个模拟节点：并发上限、单节点timeout隔离、jitter/backoff、deadline覆盖capabilities/telemetry/identity全部调用；单元模拟不是2h真实矩阵。
- Health：SUSPECT/UNREACHABLE/RECOVERING/HEALTHY、proxy与accounting分离、缺probe UNKNOWN、过期/时钟偏差、计数复位/instance切换。
- SQLite：事务重启、并发、乱序写入拒绝、坏行/坏DB/坏rollup容错、raw/rollup时钟推进清理、行数cap与截断标记。长保留期通过fixture验证，非90天实测。
- CLI/UI共享cache服务；UI GET通过禁止SSH的mock断言并比对DB字节，空cache读取不创建目录/DB。
- probe：专用profile合同、唯一VLESS outbound、loopback inbound、curlrc/env绕过阻断、timeout子进程回收；真实VLESS/HTTPS连接待Live。
- accountd：projection不含用户UUID/Reality私钥；atomic publish注入失败不覆盖旧值；格式/权限拒绝；坏/异身份mapping保留旧值，无规范文件fallback。
- Linux权限：UID 998子进程读最小投影、写SQLite，不能读root规范secret或改投影；拒绝symlink/hardlink；restore后owner/instance更新；Unix socket对非组UID 999拒绝，对UID 998允许。
- observer：命令注入/extra args/mutation拒绝、Ed25519公钥不能覆盖forced-command、Unix peer协议、独立observe用户名不改变admin路线、没有显式observe凭据则拒绝。
- schema：实现输出与monitor/v1 schema交叉验证；缺字段、未来版本、secret/unknown字段反例。

本轮没有执行真实VPS、sshd登录/转发、systemd运行时sandbox、2h/24h soak或远端CI；相关项不填写PASS。
