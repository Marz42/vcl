# 0.5.2 M1 本地候选制品

日期：2026-10-04；起点 `fabe8f1`；本轮实际输入见 [SOURCE_INPUTS.json](SOURCE_INPUTS.json)。构建固定 `SOURCE_DATE_EPOCH=1790679997`，从 LF / Git mode 的隔离 Linux 源码副本生成。

**名称/stamp 仍为 0.5.1**：这是未发布的 M1 开发候选，不能当作完整 0.5.2 RC。新 Controller 包已含 Findings/Timeline；Node 实现和版本合同未改变。不同构建 epoch 的旧 CI 摘要不能直接用来比较本轮候选。

| 制品 | SHA-256 |
| --- | --- |
| `vincula-node-0.5.1.tar.gz` | `a8cda56a009a9e78bd3a7f25ee162fd236cdce45430ddb401db28a650e70fd43` |
| `vincula-controller-0.5.1.zip` | `74bf91c06e0179ff893e6e592682ec2820b665c9b23d16990d0f1056702f8c8a` |
| `payload-manifest.json` | `e1f49d74facbc04ed2ae3ddd40f18aa221a53b3fdd3357081eddb0acbb44044f` |

Node release.lock、两包 sidecar、Controller controller.lock 和包内 `lib/observation/findings.py` 成员检查通过。Controller ZIP 解压到无 repo lib 的独立目录，以 Python `-I` 执行 `init`、`findings --json`、`timeline --json`；只读命令不创建 observation/findings DB，不改变 init 后文件内容。

本机制品与原始日志位于 `tmp/linux-validation-20261004-verified/`，未上传、未发布。**G4/soak：PENDING LIVE；Human Gate H05：PENDING HUMAN；完整 0.5.2：IN PROGRESS。**
