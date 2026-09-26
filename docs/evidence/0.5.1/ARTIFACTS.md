# 0.5.1 本地制品与源码绑定

构建状态：**PASS LOCAL**。制品保留在仓库忽略的`dist/`，本轮不上传、不tag、不发布。

- Base commit：`f38b29260a459b8b252df9dd0774d5f754401946`。
- 固定`SOURCE_DATE_EPOCH=1790386657`。
- 源码来自本次未提交候选的POSIX/LF规范化副本；正式交付commit包含相同源码与本地记录，提交SHA通过git历史定位。
- [`SOURCE_INPUTS.json`](SOURCE_INPUTS.json)记录实际构建/测试输入逐文件SHA及清单自身digest；100项输入已逐项核对与最终工作树的Git规范化内容一致。

| 产物 | SHA-256 |
| --- | --- |
| `dist/vincula-node-0.5.1.tar.gz` | `a12208c20acb71b9a6e3f1424eb2c988a263da47876652b7cc161d3a37c2003e` |
| `dist/vincula-controller-0.5.1.zip` | `a863277099ceae9ab59e3bd32ab9c4a61776711639b2c3d128893448694e0a99` |
| source inputs | `e566a99512c5f7e442faedd5045caa92ebfbca063ee39696d3affd160021914f` |

Node `release.lock`、Controller `controller.lock`与archive sidecars必须全部通过；Controller black-box包检验不得依赖源码目录。未来重新构建或修改打包输入时需重新记录digest，不能沿用本页值。
