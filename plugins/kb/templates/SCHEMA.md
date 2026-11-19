---
schema_version: 1
---
# 知识库契约

机器规则由 kb check 实现；本说明可以补充写作约定，修改正文不会改变校验规则。

## 目录

- SCHEMA.md：本契约，schema_version 必须是整数 1。
- index.md：按页面类型分节的总目录，每页仅出现一次。
- log.md：按时间从旧到新，只追加的操作日志。
- inbox/：经验原文，只追加，写入后不可改、不可删。
- raw/：外部资料原文，同样只追加，不可改、不可删。
- wiki/pitfalls/、wiki/decisions/、wiki/tech/、wiki/patterns/、wiki/projects/：编译后的页面。
- templates/：pitfall.md、decision.md、tech.md、pattern.md、project.md 写作模板。

inbox/ 和 raw/ 的已提交文件由 git 与最近一次提交比较；工作区修改、删除都报错，未跟踪的新文件允许追加。知识库必须是独立 git 仓库。新增原文校验后应提交保存基线。

## 页面 frontmatter

| 字段 | 必填 | 格式与含义 |
| --- | --- | --- |
| type | 是 | pitfall / decision / tech / pattern / project，分别对应上述五个 wiki 子目录 |
| title | 是 | 非空中文标题 |
| status | 是 | current / superseded |
| superseded_by | status 为 superseded 时 | 知识库根目录相对路径，指向存在的 wiki 页面 |
| created | 是 | YYYY-MM-DD，不晚于本机时区今天 |
| updated | 是 | YYYY-MM-DD，不晚于今天，且不早于 created |
| raw | project 以外必填 | 非空字符串列表；根目录相对路径，只能指向存在的 inbox/ 或 raw/ 文件 |
| tags | 否 | 字符串列表 |
| projects | 否 | 项目代号字符串列表，如 proj-example |

文件名只用英文 kebab-case，以 .md 结尾，整个文件名不超过 60 个字符。

## 五种页面必备章节

以下章节必须使用二级标题（##）：

| 类型 | 章节 |
| --- | --- |
| pitfall | 症状 / 原因 / 解法 / 适用范围 / 如何验证 |
| decision | 背景 / 选项 / 决定 / 理由 / 后果 |
| tech | 原理 / 用法 / 坑 / 搭配 / 最佳实践 |
| pattern | 问题 / 方案 / 适用条件 / 反例 |
| project | 概况 / 相关坑 / 相关决策 |

## 链接与出处

正文使用相对 Markdown 链接，如 `[相关坑](../pitfalls/example.md)`、`[现行判据](#现行判据)`；目标文件和标题锚点必须存在。锚点按 GitHub 标题规则生成，支持中文。frontmatter 的 raw、superseded_by 使用知识库根目录相对路径。
不使用 `[[wikilink]]`。请在 Obsidian 中关闭“使用 Wiki 链接”。
出处只写在 frontmatter raw 列表，不在正文另设出处字段。具体数字、日期、版本和长引用应逐字取自原文；标注块内也校验。小的普通整数不属于逐字校验候选。

## 结论与标注块

**标注块以外都是现行结论。** 被推翻的旧结论整段移入 outdated 块；标题行必须有合法日期和指向取代者的链接：

```markdown
> [!outdated] 2026-10-06 → [现行判据](#现行判据)
> 旧结论及其证据。
```

争议放入非空的 disputed 块，列出各方说法和出处：

```markdown
> [!disputed]
> 各方说法和证据。
```

允许 Obsidian 自带的 note、abstract、info、todo、tip、success、question、warning、failure、danger、bug、example、quote 及其标准别名；不允许其他自定义类型。
整页被取代时写 status: superseded，并用 superseded_by 指向取代页面。过时和争议内容仍须有 raw 证据。

## inbox 条目

文件名为 inbox/YYYY-MM-DD-<slug>.md，slug 为英文 kebab-case；frontmatter 字段如下：

| 字段 | 必填 | 格式 |
| --- | --- | --- |
| captured | 是 | YYYY-MM-DD，与文件名日期相同，不晚于本机今天 |
| source | 是 | session / delegate / manual |
| host | 是 | claude-code / codex / unknown |
| project | 否 | 项目代号字符串 |

正文自由文本。inbox 只追加，原文不可改、不可删；纠错请另加条目。

## index 与 log

index 按类型分节，每页恰好一行：
`- [标题](wiki/pitfalls/example.md) — 一句话摘要 · YYYY-MM-DD`

log 每条以 `## [YYYY-MM-DD] <操作> | <标题>` 开头；操作只能是 init、save、compile、lint、archive、promote，标题不能为空，日期合法且不晚于今天，按旧到新追加。

## frontmatter 语法子集

使用首尾各一行 ---。只支持顶层扁平的 key: value、[a, b] 行内字符串列表以及 - a 块字符串列表（列表项可统一缩进）。字符串可用成对单引号或双引号包裹，不支持引号转义。schema_version 使用整数。
不支持嵌套映射、嵌套列表、多行值、锚点、别名、标签、合并键或其他 YAML 语法；不支持注释。解析错误会按原始行号报告 frontmatter。

## 禁止写入的敏感内容

不得写入客户名、品牌、域名、内部 URL、IP、账号、密钥、业务数据、真实用户信息。项目统一使用代号（例如 proj-example）；原文进入 inbox/、raw/ 前也必须先脱敏。

写入前用 `kb.py redact <文件|->` 扫描草稿：先替换项目代号，再扫描密钥、网络标识、邮箱与黑名单；代码块同样扫描。命中会拒绝通过，报告类别、文件、行列和打码片段，不回显完整敏感值。`kb check` 对 inbox/、raw/、wiki/、index.md、log.md 做兜底扫描，不替换代号。

以下配置由你在本地维护，缺失时视为空：

| 文件 | 位置与格式 | 作用 |
| --- | --- | --- |
| 本地黑名单 | `~/.config/kb/blocklist.txt`，一行一词，去首尾空白，忽略空行和 `#` 开头的注释 | 公司、客户、品牌等词按不区分大小写的子串匹配；不进知识库、不提交 |
| 项目代号对照 | `~/.config/kb/aliases.json`，JSON 对象，如 `{"项目真名": "proj-example"}` | redact 扫描前自动替换，名称互相包含时最长优先；不进知识库、不提交；JSON 或映射格式错误会报配置错误 |
| 误报放行清单 | 知识库根目录 `redaction-allow.txt`，每行 `raw/example.md 0123456789abcdef  # 说明` | 提交进知识库，仅存相对路径与命中内容的 SHA-256 前 16 位十六进制，不存原文；只放行同路径同内容，换文件或内容即失效 |

设置 `KB_CONFIG` 时，blocklist.txt 与 aliases.json 跟随该配置文件所在目录；放行清单仍位于配置指向的知识库根目录。放行清单忽略空行、`#` 注释及行尾说明，格式错误按原始行号报告 redaction 问题。
