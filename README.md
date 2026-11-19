# kb

在 Claude Code 与 Codex 中使用同一个本地知识库。当前版本 `0.1.0` 仅实现插件外壳、位置配置与自检，要求 Python 3.9 或更高版本，无第三方依赖。

## 安装

把下面的 `/绝对路径/kb-plugin` 替换成本仓库路径。

Claude Code：

```bash
claude plugin marketplace add /绝对路径/kb-plugin
claude plugin install kb@kb-marketplace
```

Codex：

```bash
codex plugin marketplace add /绝对路径/kb-plugin
codex plugin add kb@kb-marketplace
```

安装后打开新会话，运行或触发 doctor skill。两个宿主共用 `plugins/kb/skills/` 与 `plugins/kb/scripts/`。
真实宿主安装仍待单独验收；以上命令不会在自动测试中执行。

## 命令清单

| 命令 | 状态 | 用途 |
| --- | --- | --- |
| `/kb:doctor` | 已实现 | 检查配置、显示知识库位置并自检 |
| `/kb:save` | 未实现 | 后续实现知识保存 |
| `/kb:ask` | 未实现 | 后续实现知识查询 |
| `/kb:lint` | 未实现 | 后续实现知识库检查 |

也可以直接使用脚本。从任何目录调用时，把脚本路径替换为本仓库内的绝对路径：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py doctor
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py doctor --json
```

doctor 检查配置、知识库目录是否存在和可读取、Python 版本是否满足要求，不进行知识操作。
退出码：`0` 成功，`1` 自检发现问题，`2` 配置或用法错误。

## 配置知识库位置

默认配置文件为 `~/.config/kb/config.json`，格式为：

```json
{
  "version": 1,
  "vault": "/绝对路径/知识库"
}
```

知识库必须是已存在的目录；脚本不创建知识库。先预览，确认路径和内容后再加 `--confirm` 写入：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py config set-vault /绝对路径/知识库
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py config set-vault /绝对路径/知识库 --confirm
```

预览不会创建配置文件或其父目录，也不会覆盖已有配置。显式传入相对路径时，`set-vault` 会将它转换为绝对路径保存。
doctor 只读取配置中的绝对路径，绝不按当前目录猜测知识库；配置缺失或无效时会报出配置文件路径和修复命令。

测试使用环境变量 `KB_CONFIG` 覆盖配置文件位置。对预览、写入与自检使用同一变量即可隔离真实配置：

```bash
export KB_CONFIG="/临时目录/kb-config.json"
```

`config set-vault` 也支持 `--json`。JSON 模式均只输出一个对象：doctor 固定字段为 `ok`、`config`、`vault`、`checks`、`error`；set-vault 固定字段为 `ok`、`config`、`content`、`written`、`error`。
`content` 是将写入的配置对象；`written` 表示是否已写入。失败时 `error` 给出中文原因。

## 卸载

Claude Code：

```bash
claude plugin uninstall kb@kb-marketplace
claude plugin marketplace remove kb-marketplace
```

Codex：

```bash
codex plugin remove kb@kb-marketplace
codex plugin marketplace remove kb-marketplace
```

卸载后打开新会话。宿主卸载不会删除知识库，也不会删除 `~/.config/kb/config.json`（或 `KB_CONFIG` 指定的文件）。不再使用时，可自行删除该配置文件；知识库按需保留。

## 开发验证

在仓库根目录执行：

```bash
python3 -m unittest discover -s tests -v
python3 -B scripts/check-manifests.py
```

所有测试都将 `KB_CONFIG` 指向临时目录，不读写真实配置，不安装插件。
根目录解析测试使用假的 `codex`，清单失败测试只修改临时副本。
