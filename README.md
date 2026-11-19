# kb

在 Claude Code 与 Codex 中使用同一个本地知识库。当前版本 `0.1.0` 已实现插件外壳、位置配置、自检、知识库初始化、契约校验与脱敏扫描，要求 Python 3.9 或更高版本，无第三方依赖。

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
以上命令已在本机两个宿主实测通过（2026-11-19）；自动测试不会执行它们。

### 更新插件后

- **Claude Code**：本地目录市场直接读取仓库内的 `plugins/kb`，改动后打开新会话即可生效。
- **Codex**：安装时会把插件复制到缓存（`~/.codex/plugins/cache/kb-marketplace/kb/<版本>`），skill 文本读的是这份副本。改动 skill 后重新执行一次安装命令刷新缓存，再打开新会话：

  ```bash
  codex plugin add kb@kb-marketplace
  ```

  `codex plugin marketplace upgrade` 只刷新 Git 来源的市场，对本地目录市场无效。

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

## 写入前脱敏

把草稿写入知识库前，先扫描文件或标准输入：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py redact /临时目录/草稿.md
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py redact /临时目录/草稿.md --json
cat /临时目录/草稿.md | python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py redact -
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py redact /临时目录/草稿.md --apply-aliases
```

redact 先按本地对照替换项目真名，再扫描密钥与凭证、IPv4、内网主机名、邮箱和本地黑名单，包含代码块。不做熵值检测；占位符、文档示例 IP 和 example.com/example.org/example.net 及其子域邮箱会排除。
默认只输出替换数与打码后的发现，不修改文件。退出码：`0` 无问题，`1` 命中敏感内容或放行清单格式错误，`2` 配置、用法或读取错误。标准输入的路径记为 `<stdin>`；库内文件使用知识库相对路径，便于匹配放行清单。

`--json` 输出 `{ok, replaced, findings}`，每条发现包含 `code: "redaction"`、`category`（secret/network/email/blocklist）、`path`、`line`、`column`、`masked`。行列从 1 开始，位置以别名替换后的文本为准。报错只输出中文原因，不包含输入原文。
`--apply-aliases` 将替换后的安全文本原样写到 stdout，替换数写到 stderr，不写文件；若仍有命中，stdout 为空，stderr 给出打码报告并退出 1。它与 `--json` 是互斥的输出模式。

三个配置文件由你维护：

| 文件 | 位置、格式与作用 |
| --- | --- |
| `blocklist.txt` | 默认 `~/.config/kb/blocklist.txt`，一行一词，去首尾空白，忽略空行与 `#` 开头的注释。不区分大小写，按子串拦截公司、客户、品牌等名称；本地保存，不进知识库、不提交 |
| `aliases.json` | 默认 `~/.config/kb/aliases.json`，例如 `{"项目真名": "proj-example"}`。名称区分大小写、字面替换，互相包含时最长优先，一次替换不递归；本地保存，不进知识库、不提交。格式错误退出 2，替换后残留的黑名单词仍会报错 |
| `redaction-allow.txt` | 位于知识库根目录，进 git，每行 `相对路径 SHA-256前16位十六进制 # 说明`，例如 `raw/example.md 0123456789abcdef # 人工确认的误报`。仅存路径和哈希，不存原文；只有同路径、同命中内容才放行，换文件或改内容后失效。空行、`#` 注释忽略，格式错误报告原始行号 |

blocklist.txt 与 aliases.json 始终跟随配置文件所在目录；设置 `KB_CONFIG=/临时目录/config.json` 后，它们也位于 `/临时目录/`，不读取默认目录。三个文件缺失均视为空；未配置知识库时也能运行 redact，仅不读取知识库放行清单。
放行哈希取扫描实际命中的完整片段，以 UTF-8 编码计算 SHA-256 后截取前 16 位；不要把敏感原文写进放行清单或注释。相同文件中相同内容的重复出现共享同一条放行记录。

`kb check` 已注册 redaction，检查 inbox/、raw/、wiki/、index.md、log.md；它读取黑名单与放行清单，扫描原文，不进行别名替换。指定路径时扫描对应内容，index、log 与放行清单格式仍作全局检查。模板与 SCHEMA.md 不属于脱敏扫描范围。

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
知识库测试把合法样例和 AC6 三段素材样例复制到临时目录，用临时 git 仓库提交基线；覆盖全部 13 个检查码、证据回归、只读检查和初始化不覆盖行为。脱敏测试在运行时拼接假密钥，覆盖规则反例、别名、哈希放行、输出打码，以及会话摘录的 3 处命中与 1 处替换。vendor 原文件及许可证的 SHA-256 也在测试中核验。
