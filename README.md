# kb

在 Claude Code 与 Codex 中使用同一个本地知识库。当前版本 `0.1.0` 已实现插件外壳、位置配置、自检、知识库初始化、契约校验、脱敏扫描、知识保存、检索与确定性体检，要求 Python 3.9 或更高版本，无第三方依赖。

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
| `/kb:save` | 已实现 | 草稿校验、预览，确认后保存一条经验并本地提交 |
| `/kb:ask` | 已实现 | 只读检索知识库，基于候选页面回答并附出处，区分现行、过时与争议内容 |
| `/kb:lint` | 已实现 | 按影响分组体检知识库，提示维护事项，预览并确认后执行三类安全修复 |

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

## 保存一条经验

一次 save 的流程是：草稿目录 → preview → 用户明确确认 → apply --confirm <指纹>。
模型负责提炼和选择新建、并入、冲突或没有新内容；脚本负责脱敏、全量契约检查、写入与本地提交。
先确保知识库已由 init 初始化并提交骨架，且工作区没有未提交改动。

草稿目录放在知识库之外，结构镜像知识库相对路径：必须恰好包含一个 `inbox/` 下的新文件，另可包含 `wiki/` 下的新建或修改文件、`index.md`、`log.md`。
禁止修改已有 inbox、写入 raw、符号链接、越界或 `..` 路径，不支持删除；未放入草稿的已有文件保持原样。

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py save preview /临时目录/kb-save-草稿
# After explicit user confirmation, use the preview fingerprint:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py save apply /临时目录/kb-save-草稿 --confirm <指纹>
```

preview 先使用真实配置目录的 `aliases.json` 替换代号，再扫描敏感内容，在保留 git 历史的临时副本上执行全部检查；输出新建、修改文件、unified diff、替换数和 16 位预览指纹，不修改知识库或草稿。
apply 重跑同样的校验并比较指纹；知识库 HEAD、工作区状态、草稿原文或替换后的内容变化都会使确认失效，需要重新 preview。
普通脏工作区拒绝为 `1`；拿先前预览指纹对变化后的工作区执行 apply 返回 `3`。
校验和指纹通过后，用同目录临时文件逐个原子替换；写入失败回滚本次文件改动。随后只暂存本次文件并执行本地 `save: <标题>` 提交，不 push。
标题优先取 inbox 对应 wiki 主页面的 frontmatter title；没有新内容时取 inbox 的 title，缺省使用 inbox 文件名。
提交失败时保留已写入文件与暂存状态，报告打码后的原因，不自动 reset。

两条命令都支持 `--json`：preview 固定字段为 `{ok, fingerprint, created, modified, diff, replaced_aliases, findings}`；apply 为 `{ok, commit, created, modified, findings}`。
findings 使用中文原因和打码后的敏感值。退出码：`0` 成功，`1` 校验或脱敏失败、写入或提交失败，`2` 用法或配置错误，`3` 指纹不匹配。

## 查询知识库

在任意项目中运行 `/kb:ask <问题>`，或直接调用确定性的只读检索脚本：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py ask search 缓存 cache 插件 --json
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py ask search 派活 成本 --limit 5
```

多个词按任意一个命中匹配，不区分大小写，正则特殊字符作为字面量处理。范围为 `wiki/` 的 Markdown 页面，frontmatter 不产生命中，index 只对对应页面加权。代码块内同样检索。
每条命中标记 `current`、`outdated` 或 `disputed`；`status: superseded` 的页面所有命中都为 outdated，同时返回取代页面路径。
排序按不同命中词计分，标题与 index 加权，只有 outdated 命中的页面排在含现行或争议命中的页面之后；同分按更新日期新到旧、路径升序。默认返回 10 页，每页最多 20 条命中行。

退出码：`0` 有命中，`1` 无命中（`--json` 仍返回合法 JSON，`pages` 为空），`2` 配置或用法错误。正常 JSON 输出为 schema 1，包含知识库绝对路径、检索词、候选页面、得分、来源、区域与原始行号；`truncated` 表示是否因页数限制省略候选。
检索只读取配置的知识库，不写文件、不修改 Git 状态。其他插件可通过 [interface.json](plugins/kb/interface.json) 探测契约 `1.0`，参数模板、字段、退出码、版本规则与静默探测方式见[接口契约说明](plugins/kb/references/interface.md)。

## 体检与安全修复

运行 `/kb:lint`，或直接调用脚本；报告仅输出到终端，不落盘：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint --json --stale-days 180
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint fix preview --json
# After explicit user confirmation, use the preview fingerprint:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint fix apply --confirm <指纹> --json
```

报告包含全部 `kb check` 问题，按导航断裂 → 内容可信度 → 格式 → 维护提示排列，每组给出数量，末尾给出摘要。维护提示包含：没有其他 wiki 页面链接的孤儿页（index 链接和自身链接不算，project 页面除外）、`current` 且距 `updated` 超过阈值的疑似过期页、未被任何 wiki frontmatter `raw` 引用的 inbox 积压。
默认过期阈值为 180 天，`--stale-days N` 可指定正整数；恰好 180 天不报。任意 save 日志条目正文中写明知识库相对路径 `inbox/…md` 的文件，会从积压中排除；“没有新内容”的 save 也应按此记录路径。
维护提示不影响 `kb check` 或 lint 的 check 级结果。规模指标单列 wiki 页数与 index.md 字节数，超过 300 页、40960 字节时提示；ask 尚未记录读取文件数，平均值如实显示“暂无数据”。

安全修复只生成以下三类草稿：

- wiki 页未进 index：在对应类型二级标题下补 `- [title](wiki/目录/文件.md) — （待补摘要） · updated`。
- index 指向不存在的页面：删除该目录行。
- wiki 页面中的库内 Markdown 链接目标不存在，且 `wiki/` 下恰好只有一个同名文件：改为正确相对路径，保留锚点；有多个候选时不修。

preview 复用 save 的共享写入流程，在保留完整 Git 历史的叠加副本上全量检查，给出 diff 与 16 位指纹；没有可修复项时退出成功并说明“无需修复”。全量检查仍有问题时拒绝写入，需要先处理这些问题。
用户明确确认后，apply 重新生成草稿、校验指纹与全部契约，通过后原子写入，并将修复与追加的 `## [今天] lint | 安全修复 N 处` 日志一起本地提交，提交信息为 `lint: 安全修复 N 处`，不推送。
修复仅允许修改 `index.md`、`log.md` 与 `wiki/` 下已存在的页面，不涉及 inbox/raw，不受 save 恰好一个 inbox 的限制。知识库需已有 HEAD 且工作区干净；写入失败回滚，提交失败保留文件与暂存状态并报告原因。

退出码：`lint` 为 `0` 无 check 级问题（可有提示）、`1` 有 check 级问题、`2` 用法或配置错误；`lint fix` 为 `0` 成功（含无需修复）、`1` 校验、写入或提交失败、`2` 用法或配置错误、`3` 指纹不匹配。
`--json` 报告包含有序 `groups`、`hints`、`metrics`、`fixable` 数量与 `summary`；`metrics.ask_average_reads.value` 为 `null`，并带 `reason`。修复结果另含 `findings`、`created`、`modified`，preview 带 `diff` 和 `fingerprint`，apply 带 `commit`。

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
save 测试覆盖路径白名单、脱敏与代号替换、完整历史校验、指纹失效、写入回滚和提交失败；另在 init 创建的临时知识库中，用三段素材连续保存新坑页、新决策页和推翻旧结论的 outdated 块，每次检查为零问题，并核验三个 save 提交与 inbox 原文不可改性。
ask 测试覆盖区域与代码块、整页 superseded、计分排序、截断、多词字面匹配、JSON 契约与退出码，以及干净和脏知识库中文件及 Git 状态保持不变；interface 检查在临时副本构造 ask skill，覆盖契约缺失、格式错误、版本和技能引用。

lint 测试覆盖提示边界、日志排除、分组与规模指标、四类问题验收、三类安全修复、歧义候选、指纹失效、修复与日志同次提交，以及只读前后文件与 Git 状态不变；共享 writer 的重构由原有 save 测试和 lint 测试共同保护。
