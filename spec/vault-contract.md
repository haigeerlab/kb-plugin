<!-- spec-guard: review approved ed5882d1b362 -->

# Spec: vault-contract

## Objective

能力图第 2 个模块。定下知识库的"契约"：目录结构、页面和 inbox 条目的格式、结论状态的写法，并用一个确定性的校验命令 `kb check` 把契约变成"写错了就过不去"的约束。后续的 save、ask、lint、compile 全部按这份契约读写，save 在写入 wiki 之前必须先过 `kb check`。

用户：
- **你**：在 Obsidian 里读知识库；偶尔手改页面后跑 `kb check`。
- **后续模块**：save 在写入前调用它，lint 复用它的检查结果。

成功的样子：
- 一条命令 `kb init` 就能在配置好的知识库目录里建好骨架。
- 任何不符合契约的写入都会被 `kb check` 拦下，并且能指出文件和行号。
- 被推翻的结论不靠模型理解文字，**用格式本身**就能被程序识别出来。

## 要你确认的假设

1. **目录结构**（知识库根目录）：
   ```
   kb/
   ├── SCHEMA.md      # 给人和 AI 读的约定说明（init 生成，之后归你和 AI 共同维护）
   ├── index.md       # 总目录：每页一行
   ├── log.md         # 操作日志：只追加
   ├── inbox/         # 经验原文：只追加，写入后不可改、不可删
   ├── raw/           # 外部资料原文：同样不可改（learn 模块才会用到）
   └── wiki/
       ├── pitfalls/  decisions/  tech/  patterns/  projects/
   ```
   和 PRD 一致；`raw/`、`inbox/` 都不放隐藏目录（实跑时 claude-obsidian 因为把原文放在 `.raw/` 下，图谱看不到、lint 报断链）。
2. **链接一律用相对路径的 Markdown 链接** `[标题](../pitfalls/xxx.md)`，不用 `[[wikilink]]`。理由：GitHub 和 Obsidian 都能解析，脚本校验简单可靠；Obsidian 的图谱和反向链接对 Markdown 链接同样有效。代价是在 Obsidian 里手写链接时，要把设置里的"使用 Wiki 链接"关掉。
3. **出处写在 frontmatter**：`raw: [inbox/2026-11-19-codex-exec-stdin.md]`，列表元素是知识库内的相对路径，只能指向 `inbox/` 或 `raw/`。只有一个出处字段，不在正文里再写一遍，避免两处不一致。
4. **结论状态用"过时内容收进标注块"来表达**：
   - 被推翻的旧结论整段移进 `> [!outdated] 2026-10-06 → [现行判据](#现行判据)` 块里，标注块的标题行必须带日期和指向取代者的链接；
   - 有争议的写成 `> [!disputed]` 块，里面列出各方说法和出处；
   - **规则只有一条：标注块以外的正文都是现行结论。** ask 只要跳过这两种块，就不会把过时结论当成现行答案。
   - 整页都被取代时，frontmatter 写 `status: superseded` 和 `superseded_by: <路径>`。
   - 这是对 karpathy 写法的改造：karpathy 是把状态块放在旧结论下面，程序要判断"状态块上面那段是哪段"，不可靠。
5. **出处逐字校验 vendor karpathy-llm-wiki 的 `check_evidence.py`**（MIT，提交 `eafcc77`，2026-07-24），保留许可证和出处说明。在它的基础上改三处：
   - 从 frontmatter 的 `raw` 读出处，不从正文的 `> Raw:` 行读；
   - **标注块里的内容也要校验**（原脚本第 225 行会整段跳过状态块，实跑时因此漏掉了一个植入的错误数字）；
   - 加中文引号 `「」` 的引用识别。
6. **inbox 和 raw 不可改，由 git 来判定**：`kb check` 把工作区里的 `inbox/`、`raw/` 和最近一次提交比较，已提交的文件被修改或删除就报错。因此知识库必须是 git 仓库，`kb init` 会在预览里列出 `git init`。
7. **SCHEMA.md 是给人和 AI 读的，机器规则写在代码里。** SCHEMA.md 带 `schema_version: 1`，`kb check` 只核对版本号是否匹配，不解析 SCHEMA.md 的正文。你和 AI 可以随时往 SCHEMA.md 里补写作约定，不会影响校验。
8. **日期用本机时区**（你的机器是 Asia/Shanghai），不用 UTC。
9. **本模块交付一个用户可见的 skill：`/kb:init`。** `kb check` 先作为脚本命令，供 save 调用、给你手动跑；面向用户的体检报告是 lint 模块的事。

## 契约细节

### 页面 frontmatter（所有 wiki 页）

| 字段 | 必填 | 取值 |
|---|---|---|
| `type` | 是 | `pitfall` / `decision` / `tech` / `pattern` / `project`，必须和所在目录一致 |
| `title` | 是 | 中文标题 |
| `status` | 是 | `current` / `superseded`（取 `superseded` 时 `superseded_by` 必填，并且指向存在的页面） |
| `created` / `updated` | 是 | `YYYY-MM-DD`，不晚于今天（本机时区），`updated` 不早于 `created` |
| `raw` | 是（`project` 类型除外） | 非空列表，元素指向存在的 `inbox/` 或 `raw/` 文件 |
| `tags` | 否 | 字符串列表 |
| `projects` | 否 | 项目代号列表，比如 `proj-starsaas` |

文件名：英文 kebab-case，以 `.md` 结尾，不超过 60 个字符。

### 页面正文必备章节（按类型，二级标题）

| 类型 | 必备章节 |
|---|---|
| pitfall | 症状 / 原因 / 解法 / 适用范围 / 如何验证 |
| decision | 背景 / 选项 / 决定 / 理由 / 后果 |
| tech | 原理 / 用法 / 坑 / 搭配 / 最佳实践 |
| pattern | 问题 / 方案 / 适用条件 / 反例 |
| project | 概况 / 相关坑 / 相关决策 |

### inbox 条目

文件名 `inbox/YYYY-MM-DD-<slug>.md`；frontmatter 包括 `captured`（日期）、`source`（`session` / `delegate` / `manual`）、`host`（`claude-code` / `codex` / `unknown`），以及可选的 `project`（代号）。正文是自由文本。

### index.md 与 log.md

- **index.md**：按类型分节，每页一行 `- [标题](wiki/<type>/<file>.md) — 一句话摘要 · YYYY-MM-DD`。每个 wiki 页都必须出现且只出现一次，index 里也不能有指向不存在页面的条目。
- **log.md**：每条以 `## [YYYY-MM-DD] <操作> | <标题>` 开头，操作取 `init` / `save` / `compile` / `lint` / `archive` / `promote` 之一；日期不晚于今天，并且按时间从旧到新排列（只追加）。

### `kb check` 检查项（全部确定性，不调用模型）

| 代码 | 检查 |
|---|---|
| `schema-version` | SCHEMA.md 存在，且 `schema_version` 为 1 |
| `frontmatter` | 必填字段、取值、类型和目录一致、日期规则 |
| `sections` | 按类型必备的章节齐全 |
| `filename` | kebab-case、长度不超限 |
| `link` | 正文和 frontmatter 里的知识库内链接都能解析到存在的文件或锚点 |
| `raw-ref` | `raw` 字段指向存在的、位于 `inbox/` 或 `raw/` 下的文件 |
| `evidence` | 数字、日期、版本号、长引用在 `raw` 文件里逐字存在（**标注块内也要查**） |
| `callout` | `[!outdated]` 的标题行带日期和链接；`[!disputed]` 不能为空；不允许其他自定义标注类型（Obsidian 自带的 note、tip、warning 等除外） |
| `index` | wiki 页和 index 条目一一对应 |
| `log` | 每条格式正确、日期合法且有序 |
| `immutable` | 已提交的 `inbox/`、`raw/` 文件没有被修改或删除 |
| `inbox` | inbox 条目的文件名和 frontmatter 合法 |

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py init                 # 预览将在已配置的知识库里创建什么
python3 -B plugins/kb/scripts/kb.py init --confirm       # 写入
python3 -B plugins/kb/scripts/kb.py check [--json] [路径 ...]   # 默认检查整个知识库；给路径时只检查这些页（index、log、immutable 仍做全局检查）
```

`check` 的退出码：0 表示无问题，1 表示有问题，2 表示配置或用法错误。`--json` 输出 `{ok, findings: [{code, path, line, message}]}`。

## Project Structure（本模块新增）

```
plugins/kb/
├── skills/init/SKILL.md
├── scripts/kblib/
│   ├── vault.py        # 知识库路径、目录常量、本地日期
│   ├── markdown.py     # frontmatter、章节、链接、标注块解析（跳过代码块）
│   ├── checks.py       # 各检查项，输出 Finding
│   ├── init.py         # kb init
│   └── evidence.py     # 改造自 vendor 的 check_evidence
├── scripts/vendor/karpathy-llm-wiki/
│   ├── check_evidence.py   # 原文件，未修改（sha256 967298…ee40e）
│   ├── LICENSE
│   └── README.md           # 来源、提交号、改动说明
└── templates/
    ├── SCHEMA.md
    ├── index.md  log.md
    └── pages/{pitfall,decision,tech,pattern,project}.md
tests/fixtures/vaults/    # 合法知识库与各类违规样例
```

## Code Style

延续 plugin-shell：只用标准库；标识符和注释用英文，用户可见输出用中文；每个检查是一个纯函数 `check_xxx(vault: Vault) -> list[Finding]`，`Finding(code, path, line, message)`；写操作默认只预览。

## Testing Strategy

- `tests/fixtures/vaults/valid/`：一个合法的小知识库，包含 5 种页面、inbox、标注块、出处，`kb check` 必须 0 问题。
- 每个检查码至少一个违规样例，断言 `code`、`path`、`line` 都准确。
- `evidence`：复用 karpathy 原测试里的典型用例（vendor 进来改造），并加两条回归测试：标注块里写错的数字要被抓到；`「」` 引用要被识别。
- `immutable`：在临时目录里 `git init`、提交一个 inbox 文件后再修改它，必须报错；没有提交过的新文件不报错。
- `init`：预览不写；`--confirm` 之后 `kb check` 通过；知识库目录非空时拒绝覆盖已有文件（只补缺失的文件）。

## Boundaries

- **总是**：写操作先预览；`check` 只读；所有测试用临时目录和 `KB_CONFIG`。
- **先问**：在你真实的知识库（`~/Documents/haigeerlab/kb`）里执行 `init --confirm` 和 `git init`。
- **不做**：调用模型；自动修复（那是 lint 的事）；孤儿页检测和规模指标（lint）；改写 inbox 或 raw；覆盖已有文件；第三方依赖（不引入 YAML 库，frontmatter 只支持扁平的 `key: value` 和 `[a, b]` / `- a` 列表这一受限子集，并在 SCHEMA.md 里写明）。

## Success Criteria

- **AC1** 单元测试全部通过：每个检查码都有合法用例和违规用例，违规用例的报错能准确定位到文件和行号。
- **AC2** `kb init` 预览时不写任何文件；`--confirm` 之后生成 SCHEMA.md、index.md、log.md、`inbox/`、`raw/`、`wiki/` 下 5 个子目录、`templates/`，必要时执行 `git init`；在全新的骨架上跑 `kb check`，0 问题。
- **AC3** 在已有内容的知识库上执行 `init`，只补缺失的文件，不覆盖任何已有文件，并在预览里逐个列出"跳过"的文件。
- **AC4** 标注块：把旧结论放进 `[!outdated]` 块的页面能通过校验；块的标题行缺日期或缺链接时报 `callout`；块内写错数字时报 `evidence`。
- **AC5** 已提交的 inbox 文件被改动或删除时，报 `immutable`。
- **AC6** 用实跑对比里的三段素材（codex exec 的坑、派活成本的旧结论、推翻它的实测），在测试样例里按本契约写成知识库，`kb check` 0 问题。这一条证明契约能表达真实场景。
- **AC7** vendor 目录里保留 `check_evidence.py` 原文件（sha256 和来源一致）、LICENSE 和来源说明；改造后的代码在 `kblib/evidence.py`，文件头注明出处。
- **AC8** `/kb:init` skill 在 Claude Code 里可用，并且遵守 plugin-shell 的根目录解析片段约束（片段一致性测试通过）。
- **AC9** SCHEMA.md 模板写清：目录、frontmatter 字段、5 种页面的章节、链接写法、标注块规则、inbox 规则、frontmatter 支持的语法子集、禁止写入的敏感内容（引用 PRD 6.4）。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/templates/SCHEMA.md` | 新建：知识库约定（进入知识库后归你和 AI 维护） |
| `README.md` | 更新：`/kb:init` 改为已实现，补 `kb check` 的用法 |
| `plugins/kb/scripts/vendor/karpathy-llm-wiki/README.md` | 新建：来源、提交号、改动说明 |

## Open Questions

无。（上面 9 条假设请逐条看一下，尤其是第 2 条链接写法和第 4 条结论状态写法，它们一旦定了，后续所有模块都会按它们来写。）

## 变更记录

- 2026-11-19 初稿。
