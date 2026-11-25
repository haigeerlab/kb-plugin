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
| `/kb:compile` | 已实现 | 整理 inbox 积压与候选会话，批量预览后逐条编译并本地提交 |
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

### git 身份

`save`、`compile` 和 `lint fix` 会在知识库里做本地提交，所以知识库所在目录必须能拿到 git 身份。全局设置了 `user.useConfigOnly = true`、身份只通过 `includeIf "gitdir:…"` 按目录引入时，知识库要放在被引入的目录下面（本机是 `~/Documents/haigeerlab/`）。放到其他目录时，写入会成功但提交会失败，报错为 `Author identity unknown`；文件会保留，不会回滚。

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

### 提交失败怎么办

save apply、compile apply 或 lint fix apply 已写入文件、但 `git add` 或提交失败时，会保留文件与暂存状态，并在知识库根目录生成 `.kb-pending.json`，记录本次文件的相对路径、写入后的 SHA-256、原定提交信息、操作、预览指纹和本地时间。错误消息会给出完整恢复命令：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py commit-pending
# To get a structured result:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py commit-pending --json
```

命令先核对文件内容与记录一致、工作区没有记录外的改动（含未跟踪文件），再运行全量 `kb check`；全部通过后只暂存并提交记录中的文件，沿用原提交信息，成功后删除记录并报告提交号。`.kb-pending.json` 不会被加入提交，`kb check` 和 lint 不扫描它。有记录时，save、compile 与 lint fix 的 preview、apply 都会拒绝，提示先运行 `commit-pending`。

退出码：`0` 提交成功；`1` 内容核对、工作区核对、全量检查或再次提交失败，保留记录；`2` 没有待提交记录、记录损坏或格式不符、用法或配置错误。`--json` 输出固定字段 `{ok, commit, files, findings, error}`。如果连记录也无法写入，会保留文件并报告原提交失败原因。

在 Codex 沙箱内因 `.git` 不可写而失败时，把报错中的完整命令交给用户，在 Claude Code、终端或交互式 Codex 提权后运行。不要自己执行 `git add`、`git commit`，也不要修改 `.git`；直接使用 `commit-pending` 完成核对与提交。

## 批量编译积压与候选会话

`/kb:compile` 处理两类来源：没有 wiki `raw` 引用、也没有 save 日志处理记录的 inbox 积压，以及本机队列中 `pending` 的候选会话。积压判定与 lint 共用同一函数，save 日志正文写明路径的“没有新内容”条目也会排除。

候选队列默认位于 `~/.local/state/kb/candidates.jsonl`，可用 `KB_STATE_DIR` 覆盖其父目录。它只保存本机会话指针，不放进知识库、不进入知识库的 Git 提交。每行一个 JSON 对象：

```json
{"id":"0123456789ab","session_id":"会话标识","transcript_path":"/绝对路径/会话.jsonl","cwd":"/绝对路径/项目","reason":"包含待整理经验","ended_at":"2026-11-19T16:00:00+08:00","status":"pending"}
```

`id` 是 `session_id` 的 SHA-256 前 12 位；`ended_at` 是最近入队时的本地 ISO 时间。状态为 `pending`、`compiled`、`dropped` 或 `expired`。同一 `session_id` 再次入队会更新路径、项目目录、原因和时间，`pending`/`expired` 恢复为 `pending`，`compiled`/`dropped` 保持原状态，不新增重复行。队列原子替换；损坏行跳过并报告行号，更新时保留其他行。

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates add --session-id <会话ID> --transcript /绝对路径/会话.jsonl --cwd /绝对路径/项目 --reason "待整理的经验"
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates list --json
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates show <候选ID> --max-chars 40000
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates mark <候选ID> --status compiled
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates mark <候选ID> --status dropped
```

`list` 不加 `--json` 时输出中文清单；JSON 的 `items` 合并 `kind: inbox` 积压和 `kind: candidate` 的待处理候选，`expired` 单列已过期项，`corrupt_lines` 列出损坏队列行号。会话文件不存在时自动写回 `expired`；候选距最近入队超过 25 天标为“即将过期”，恰好 25 天不标。
`show` 只支持 Claude Code JSONL：保留非 meta、非子代理的用户字符串输入（移除 system-reminder 片段）和非子代理的 assistant text 块，按【用户】【助手】顺序输出。工具结果、工具调用、思考、附件和系统注入不输出；内置脱敏规则与配置目录旁的 `blocklist.txt` 对命中片段打码，保留上下文。打码后若超过默认 40000 字，只保留结尾并标注“已截断前 N 字”，末尾报告无法解析或识别的记录数。
候选命令退出码：`0` 成功（含清单为空或跳过损坏行），`1` 业务失败（候选不存在、会话已过期或队列读写失败），`2` 用法或配置错误。`mark` 仅允许 `compiled`、`dropped`；丢弃只改队列，不写知识库。

编译分三步，用户做两次决定：

1. **清单**：列出全部积压和候选，为每项摘要并建议编译、丢弃或留着；等待用户挑选。同一会话的多条经验拆成多个清单项。
2. **批量预览**：为每个选中项建立独立草稿，逐项运行 preview，集中展示处置、文件清单、完整 diff 和指纹；等待用户确认全部或其中一部分。
3. **逐条写入**：仅 apply 已确认的项，每项独立事务、独立 `compile: <标题>` 提交，失败即停，已完成的事务保留。一个会话全部选定经验处理完后再标为 `compiled`。前一项改变 HEAD 后，后续项需重新预览并核对确认的内容；若预览内容变化，重新取得用户确认。

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py compile preview /临时目录/编译草稿 --json
# After explicit user confirmation, use the preview fingerprint:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py compile apply /临时目录/编译草稿 --confirm <指纹> --json
```

积压项草稿不新建 inbox，wiki 的 `raw` 引用已有积压文件；候选会话草稿新建一个 inbox 摘录，承重事实从会话逐字摘录。compile 允许 0 或 1 个新 inbox，2 个及以上拒绝；其余白名单、代号替换、脱敏、全量叠加检查、指纹和原子写入复用 save。禁止修改已有 inbox/raw；0 个 inbox 且没有实际改动 wiki 页面时，提示“没有可写入的内容”并拒绝。标题优先取 wiki 主页面的 title，没有 wiki 改动时取 inbox title 或文件名；日志操作名写 `compile`。

preview/apply 都支持 `--json`，字段与 save 相同。compile 退出码：`0` 成功，`1` 校验、脱敏、写入或提交失败，`2` 用法或配置错误，`3` 指纹不匹配。提交失败生成 `.kb-pending.json`，使用上面的 `commit-pending` 流程恢复；待提交期间拒绝新的写入。compile 不注册 SessionEnd hook，不读取 Codex 会话，不自动归档 ask 回答。

## 会话结束自动记候选

hook 配置在 `plugins/kb/hooks/hooks.json`，**已启用**（2026-11-19）。只用于 Claude Code，Codex 不采集。所有结束原因都会触发 SessionEnd；已实测：`claude -p` 结束时触发（reason=other），交互式会话里输入 `/clear` 时触发（reason=clear）。桌面 app 里归档或关闭会话标签页是否触发，尚未单独验证。

采集只把会话 ID、会话记录路径、工作目录、结束原因记入本机候选队列，沿用队列的短哈希、时间和处理状态，**不记录会话内容**。脚本只读取记录来计数，不摘录、不调用模型、不联网、不写知识库，也不修改配置。下次 `/kb:compile` 时再由你选择处理哪些候选。

配置 `session_capture` 默认 `true`，`capture_min_user_messages` 默认 `2`，`capture_ignore_dirs` 默认空数组。只统计非 meta、非子代理的用户消息：字符串或 text 块移除 `system-reminder`、`task-notification`、`side-sessions-event` 注入块后仍有非空文字才算一条；工具结果、附件和助手消息不计数，同一条消息含多个 text 块也只算一条。计数达到阈值就停止读取；不足阈值不入队。同一会话去重，已编译或已丢弃状态保持不变。

排除目录按规范化后的完整路径分量匹配，包括目录自身和所有子目录；`/a/b` 不会误排除 `/a/bc`。知识库目录和插件源码目录默认也可以入队。

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py capture status
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py capture status --json
# Preview first; append --confirm to write after reviewing:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled false
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled true --min-user-messages 3 --ignore-dir /项目/公司项目 /项目/自动化目录
# Clear the exclusion list:
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled true --ignore-dir
```

`set-capture` 支持 `--json`，先预览完整配置，只有 `--confirm` 才写入，并保留已有的其他字段；不传阈值或排除目录选项时保留原值。状态命令显示开关、阈值、排除目录、队列中 `pending` 数量、日志位置和最后 5 行；不更新队列状态。配置类型错误或损坏时，状态查询退出 `2`，hook 记日志并跳过。

hook 始终静默退出 `0`，超时为 5 秒。异常原因追加到 `~/.local/state/kb/capture.log`（设置 `KB_STATE_DIR` 后为该目录下的 `capture.log`），每行包含本地 ISO 时间、原因和可取得的会话 ID。日志超过 1MB 后保留后半部完整行；日志无法写入时也静默退出。正常过滤或成功入队不写日志。

## Codex 执行经验回流

Claude Code 的 SessionEnd hook 在原有会话候选采集之后，顺带读取 delegate 的公开结果文件和答复文件，将值得整理的执行结果保存为本机快照，加入 `source: delegate` 的候选队列。它独立于 `session_capture`、会话消息阈值和排除目录；不读取 Codex 自己的会话文件，不自动写入知识库。下次整理时，仍由你选择编译或丢弃。

只处理 `schema: 1`、`kind: run`，且状态为 `done`、`failed`、`timeout`、`unmarked`、`unreaped` 或 `empty` 的结果。`review`、`needs-input` 等状态跳过。同一 `chainRoot` 选择当前最后结束的 run，只收集一次；链已收集后不会追加后来者。实际答复少于字节阈值且所有命令均成功时跳过；短答复含失败命令仍收集。损坏 JSON、字段缺失、不支持的 schema、缺失答复和不可访问的目录会跳过，并在状态目录的 `capture.log` 记录原因。

配置沿用 `KB_CONFIG` 指定的 JSON 文件（默认 `~/.config/kb/config.json`），新增字段可与现有字段一起维护：

```json
{
  "version": 1,
  "vault": "/绝对路径/知识库",
  "delegate_capture": true,
  "delegate_min_answer_bytes": 200
}
```

`delegate_capture` 默认 `true`，设为 `false` 会同时关闭 hook 和手动扫描；`delegate_min_answer_bytes` 默认 `200`，允许非负整数，`0` 表示不按短答复过滤。修改阈值不重新处理此前已判定的结果。`config set-capture` 保留已设置的 delegate 字段。

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates scan-delegate
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates scan-delegate --json
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates list
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py candidates show <候选ID>
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py capture status --json
```

扫描按 runId 排序，每次最多处理 20 个新结果，其余留待下次；已收集或已跳过的 runId 都记录在状态目录下的 `delegate-scan.json`，后续不再重复判定。手动扫描只报告数量、runId 和理由，不输出答复。`capture status` 显示开关、字节阈值、最近一次扫描时间和处理个数；hook 遇到空目录时不创建扫描状态。

快照位于 `${KB_STATE_DIR:-~/.local/state/kb}/delegate/<runId>.json`，包含 runId、状态、仓库、读写模式、起止时间、改动文件、失败命令和答复。失败命令截断到 300 个字符，答复截断到 20000 个字符，不复制原始结果文件。`candidates list` 显示仓库名、状态和时间，`show` 对快照内容使用现有打码规则及本地黑名单；会话候选缺少 `source` 时按 `session` 读取，旧队列无需迁移。

**delegate 目录始终只读**：默认读取 `${TMPDIR:-/tmp}/delegate`，可用 `KB_DELEGATE_DIR` 指向其他目录；扫描不写入、不修改、不删除其中任何文件，只向本机状态目录写快照、队列、扫描状态和日志。测试同时用临时 `KB_CONFIG`、`KB_STATE_DIR`、`KB_DELEGATE_DIR` 隔离真实数据。

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

### 语义体检（可选）

需要深度体检时，可在确定性体检后提取候选包，由模型判断疑似矛盾、疑似过期、缺页概念和建议升级为规则四类问题，再核对报告的逐字引文：

```bash
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint semantic-pack
python3 -B /绝对路径/kb-plugin/plugins/kb/scripts/kb.py lint semantic-verify /临时目录/findings.json --json
```

`semantic-pack` 默认输出 JSON，`--json` 可省略；测试可用 `--today YYYY-MM-DD` 固定今天，平时默认本地日期。包中包含各页元数据、距创建和更新日期的天数、相关和正文内的 wiki 页面链接、去掉全部标注块的现行正文及四类事实线索。正文每页最多 4000 字符，整个 UTF-8 JSON 包不超过 60000 字节，优先保留 `updated` 较旧的页；`truncated` 和 `truncated_pages` 标明截断，元数据与候选仍放不下时省略较新页面，并以 `omitted_page_count` 记录数量。被省略的页面也进入截断清单；清单自身最多占 15000 字节，`truncated_page_count` 始终记录截断总页数。矛盾候选最多 30 对，线索本身不代表问题成立。

模型生成的 findings 格式如下，`category` 取 `contradiction`、`stale`、`missing-page` 或 `promote`，引文必须来自所列 wiki 页面的现行结论区：

```json
{"version": 1, "findings": [
  {"category": "stale",
   "pages": ["wiki/tech/example.md"],
   "quotes": [{"page": "wiki/tech/example.md", "text": "这里填写页面中的逐字引文"}],
   "reason": "说明为什么需要核实",
   "action": "建议重新核实后更新日期",
   "verified_by": "可选：本机只读核实命令与结果"}
]}
```

`semantic-verify -` 从 stdin 读取同样的 JSON，适用于无法写临时文件的只读沙箱。验证会拒绝越界、非 wiki 或不存在的页面路径，标注块内的旧结论不能作证；引文复用 evidence 的空白规范化和逐字包含判断。JSON 结果分为 `accepted` 和带失败理由的 `rejected`，全部内容经过现有打码规则与本地黑名单处理；省略 `--json` 时，按四类输出通过的条目，最后单列“引文核对失败，已剔除”。退出码为 `0` 全部通过、`1` 有剔除项、`2` 输入格式、配置或用法错误。

语义体检只出报告，不修改知识库、不写 log、不联网核实，也不执行升级规则；建议动作由用户决定是否另行执行。

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
kb_test_root=$(mktemp -d)
mkdir "$kb_test_root/delegate"
KB_CONFIG="$kb_test_root/config.json" KB_STATE_DIR="$kb_test_root/state" \
  KB_DELEGATE_DIR="$kb_test_root/delegate" python3 -m unittest discover -s tests -v
rm -rf "$kb_test_root"
python3 -B scripts/check-manifests.py
```

全量测试通过临时 `KB_CONFIG`、`KB_STATE_DIR` 和空的 `KB_DELEGATE_DIR` 隔离真实数据；各测试再按需覆盖为自己的临时目录。不读写真实配置、状态、delegate 结果或知识库，不安装插件。
根目录解析测试使用假的 `codex`，清单失败测试只修改临时副本。
知识库测试把合法样例和 AC6 三段素材样例复制到临时目录，用临时 git 仓库提交基线；覆盖全部 13 个检查码、证据回归、只读检查和初始化不覆盖行为。脱敏测试在运行时拼接假密钥，覆盖规则反例、别名、哈希放行、输出打码，以及会话摘录的 3 处命中与 1 处替换。vendor 原文件及许可证的 SHA-256 也在测试中核验。
save 测试覆盖路径白名单、脱敏与代号替换、完整历史校验、指纹失效、写入回滚和提交失败；另在 init 创建的临时知识库中，用三段素材连续保存新坑页、新决策页和推翻旧结论的 outdated 块，每次检查为零问题，并核验三个 save 提交与 inbox 原文不可改性。
ask 测试覆盖区域与代码块、整页 superseded、计分排序、截断、多词字面匹配、JSON 契约与退出码，以及干净和脏知识库中文件及 Git 状态保持不变；interface 检查在临时副本构造 ask skill，覆盖契约缺失、格式错误、版本和技能引用。

lint 测试覆盖提示边界、日志排除、分组与规模指标、四类问题验收、三类安全修复、歧义候选、指纹失效、修复与日志同次提交，以及只读前后文件与 Git 状态不变；共享 writer 的重构由原有 save 测试和 lint 测试共同保护。

候选与编译测试用临时 `KB_CONFIG`、`KB_STATE_DIR` 隔离配置和队列，覆盖去重、状态、损坏行、25 天边界、会话文本白名单、打码后截断，以及 compile 的 0/1/2 个 inbox、不可改原文、指纹、写入回滚和待提交恢复。端到端测试从一条积压和一条候选生成两份草稿，完成两个 compile 提交、候选标记与零问题契约检查。

会话采集测试覆盖消息过滤、阈值、目录边界、关闭、去重、异常静默与日志轮转、配置预览和保留其他字段、只读状态查询、5MB 记录提前停止读取，以及 draft 命令原样执行和清单校验；核验采集前后知识库与配置文件不变。

## 提交改动

`main` 受分支保护：不能直接推送、强推或删除，所有改动都要从分支开 PR 合入。PR 上的 CI 分别在 macOS 自带的 Python 3.9 和 ubuntu 上的 Python 3.13 跑统一检查入口 `bash scripts/validate.sh`（清单检查、本机路径检查、全量单元测试，最后列出最慢的测试文件；`--quick` 是日常快检查，只跑本分支改动涉及的测试，对应不上时退回全量），另有 `plugin validate` 任务用 `claude plugin validate --strict` 校验插件；主干只把汇总任务 `CI required` 设为必过检查，它在上述任务全部通过时才通过。CI 只使用仓库内的虚构 fixture，不读取任何真实知识库。

风险分级见 `.github/autopr/risk-tiers.yml`：脱敏模块、检查脚本与统一检查入口属于 T4，由维护者在对话里决定合并：会话开完 PR 就问「可以合并吗」，维护者回「合并」后，检查已全部通过时直接 `gh pr merge --merge`，否则 `gh pr merge --auto --merge`，由 GitHub 等 `CI required` 通过后合并；T4 永远不开「验证通过不问就合」的自动合并。
