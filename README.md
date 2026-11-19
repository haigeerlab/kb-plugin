# kb

在 Claude Code 与 Codex 中使用同一个本地知识库。当前版本 `0.1.0` 已实现插件外壳、位置配置、自检、知识库初始化与契约校验，要求 Python 3.9 或更高版本，无第三方依赖。

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
| `/kb:init` | 已实现 | 预览并确认后补齐知识库骨架，已有文件不覆盖 |
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

## 初始化与契约检查

配置指向已存在的知识库目录后，先预览创建清单、跳过清单和是否执行 `git init`；确认后才写入：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py init
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py init --confirm
```

`/kb:init` skill 会先运行预览、原样转述结果，等待明确同意后再执行确认命令。
init 只补缺失的文件与目录，绝不覆盖已有文件；仅在知识库尚未拥有独立 git 仓库时执行 `git init`。
生成 SCHEMA.md、index.md、log.md、inbox/、raw/、wiki/ 下五个类型目录，以及 templates/ 中的五种页面模板。日期取本机时区。
init 支持 `--json`，字段为 `ok`、`vault`、`create`、`skip`、`git_init`、`written`、`error`；目录项以 `/` 结尾，预览不写文件。退出码 `0` 表示成功，`2` 表示配置、用法或初始化错误。

只读校验契约：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py check
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py check --json
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py check wiki/pitfalls/example.md wiki/decisions
```

路径相对于配置的知识库根目录解析，不受命令当前目录影响；也可传入库内绝对路径。默认检查整个知识库，指定路径只检查对应页面，schema、index、log、immutable 仍做全局检查。
退出码：`0` 无问题，`1` 发现契约问题，`2` 配置或用法错误。中文输出给出文件、原始行号、检查码与原因。
`--json` 标准输出固定为 `{ "ok": true, "findings": [] }`；每个问题包含 `code`、`path`、`line`、`message`。配置或用法错误返回 `ok: false`、空 findings，并把中文原因写到标准错误。

具体写作规则见初始化生成的 SCHEMA.md。正文使用相对 Markdown 链接，在 Obsidian 中关闭“使用 Wiki 链接”；旧结论整段放入 outdated 标注块，争议放入 disputed 块，块内也校验证据。
`inbox/`、`raw/` 已提交的原文被修改或删除会报 immutable；新增文件允许追加，校验后应提交到知识库建立不可改基线。check 不调用模型、不自动修复、不提交文件。

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
知识库测试把合法样例和 AC6 三段素材样例复制到临时目录，用临时 git 仓库提交基线；覆盖全部 12 个检查码、证据回归、只读检查和初始化不覆盖行为。vendor 原文件及许可证的 SHA-256 也在测试中核验。
