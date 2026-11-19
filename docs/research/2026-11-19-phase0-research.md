# PCKS Phase 0 调研报告

> 日期：2026-11-19 · 状态：待确认
> 范围：Karpathy LLM Wiki 原文核实；开源实现源码级审查；自有插件扩展点盘点；基座推荐。
> 源码均为浅克隆后阅读，数据（star、最近提交）为 2026-11-19 通过 `gh api` 实取。

## 1. Karpathy 原文核实

来源：gist `442a6bf555914893e9891c11519de94f`，文件 `llm-wiki.md`，约 2000 词。gist 只有一个修订（2026-04-04 16:25 UTC），**发布后没改过**。

| 构想里的说法 | 原文实际 | 结论 |
|---|---|---|
| raw / wiki / schema 三层 | 原文就是这三层。schema 明说"例如 Claude Code 的 CLAUDE.md、Codex 的 AGENTS.md"，并且**和 LLM 一起共同演化** | ✅ 一致 |
| ingest / query / lint 三操作 | 一致。ingest"一个源可能触及 10–15 个页面"；作者本人偏好**一次一个源、人在环里**，批量也可以 | ✅ 一致 |
| index.md | 面向内容的目录：每页一行链接 + 一句摘要 + 可选元数据，按类别分组；**每次 ingest 都更新**；query 时先读 index 再下钻。原文称在 ~100 个源、几百页规模下"出奇地好用"，可以不上向量 RAG | ✅ 一致，阈值有原文依据 |
| log.md | 按时间、**只追加**；建议统一前缀 `## [YYYY-MM-DD] ingest \| 标题`，这样 `grep "^## \[" log.md \| tail -5` 就能解析 | ✅ 一致 |
| 查询结果回写 wiki | 原文原话：好的回答"可以作为新页面归档回 wiki"——比较、分析、发现的关联不该消失在聊天记录里 | ✅ 一致；但原文是"可以"，没说自动 |
| lint 内容 | 页面间矛盾、被新源取代的过期结论、无入链的孤儿页、提到了却没有独立页的概念、缺失的交叉引用、可以联网补的数据缺口 | ✅ 比构想多两项：**缺页概念**、**数据缺口** |
| hot.md | **原文没有**。是 claude-obsidian 自己加的 | ⚠️ 构想里标"借鉴 claude-obsidian"是对的，但不是 Karpathy 的东西 |
| 检索工具 | 原文推荐 `qmd`（本地 BM25 + 向量 + LLM 重排，CLI + MCP）。实测：★31k，最新 `@tobilu/qmd@2.9.0`，2026-11-18 仍有提交，MIT | 日后检索升级的首选候选 |

**和 PCKS 的根本差异**：原文的输入是"你挑选的外部资料"（文章、论文、书），人负责 sourcing。PCKS 的主要输入是**工作过程中产生的经验**（bug 根因、技术决策、踩坑），来源是会话本身。这一点决定了下面所有实现都只能借鉴、不能直接套用——见第 3 节。

## 2. 开源实现对比

### 2.1 总表

| | claude-obsidian | karpathy-llm-wiki | llm_wiki（nashsu） | llm-wiki-agent | llm-wiki-compiler | llm-wiki-skill（sdyckjq） |
|---|---|---|---|---|---|---|
| 形态 | Claude Code 插件 + Agent Skills + Python 内核 | **单个 Agent Skill** + 1 个校验脚本 | Tauri 桌面应用 | 仓库模板（CLAUDE.md/AGENTS.md + .claude/commands） | npm CLI + SDK + MCP | Agent Skill + TS 依赖 |
| ★ / 最近提交 | 16.6k / 2026-10-22 | 2.8k / 2026-07-24 | 21.7k / 2026-10-21 | 3.7k / 实际代码停更（近期只有 star-history 机器人提交） | 2.3k / 2026-11-14 | 2.6k / 2026-07-27 |
| 许可证 | MIT | MIT | **GPLv3**（GitHub 显示 NOASSERTION） | MIT | MIT | **仓库无 LICENSE 文件**（只在 SKILL frontmatter 写了 MIT） |
| 体量 | ~23.6k 行 Python，15 skill，45 个测试文件 | SKILL 14KB + 431 行脚本 + 765 行测试 | ingest.ts 一个文件 3940 行，152 个 TS 测试 | ~3.3k 行 Python | ~43 万行（含文档） | ~11 万行（含 vendored 依赖） |
| Codex 兼容 | ✅ `AGENTS.md` + 安装脚本把 skills 软链到 `~/.agents/skills/` | ✅ 复制到 `.agents/skills/` | ⚠️ 只能把 Codex 当 LLM 后端，离不开桌面进程 | ✅ AGENTS.md | 走自己的 provider | ✅ |
| 目录 | `inbox/` `.raw/` `wiki/{concepts,entities,sources,questions…}` `wiki/meta/ledgers/` `.vault-meta/` | `raw/<topic>/` `wiki/<topic>/`（只允许一层） | `raw/sources` `wiki/{entities,concepts,sources,queries,comparisons,synthesis}` `schema.md` `purpose.md` | `raw/` `wiki/{sources,entities,concepts,syntheses}` | 配置化 profile | 类似 |
| 输入定位 | 外部资料 + 选定的对话内容（`save`） | 外部资料 | 外部资料 | 外部资料 | 外部资料 | 外部资料（网页/推特/公众号…） |

**结论**：后三个不进入候选——llm-wiki-agent 实际已停更；llm-wiki-compiler 是独立 CLI，自带 provider，和"由 Claude Code / Codex 本身读写"的形态相反；sdyckjq 的仓库没有 LICENSE 文件，法律上不能复用。下面只展开前三个。

### 2.2 claude-obsidian（最成熟，也最重）

**做得好的（源码证据）**
- **采集和入库分离**：`inbox/` 是可见的采集区、永不自动删除；`.raw/` 只允许 create，不允许改（`AGENTS.md` "Vault conventions"）。和 PCKS"采集要随便，入库要严格"的原则一致。
- **事务式写入**：一次知识操作是一个 `claude-obsidian.transaction.v1` bundle。每个目标文件记录预期 SHA-256，先 `workflow inspect` 出预览，拿 `approval_sha256` 才能 `apply`；冲突时退出码 75，可以 `transaction recover`（`skills/wiki-ingest/SKILL.md` "Preview, apply, and recover"）。这是本次调研里"用结构让错误不可能发生"做得最彻底的一个，和你的 constraint = quality 最合拍。
- **ingest 有"编译价值门槛"**：只有能带来持久的综合、导航、决策或可复用关联时才新建或扩写页面，否则只记源、不出页（同文件 "Analyze before drafting" 第 3 步）。
- **按来源类型分别分析**：code / research / decision / conversation 各看不同的东西（第 2 步）。decision 类看"理由、负责人、结果"，可以直接用在 ADR 页。
- **出处账本**：source ledger + claim ledger 分开记，"高风险结论需要两个独立来源"，对话里的断言不算独立证据（`save/SKILL.md` "Preserve evidence honestly"）。
- **save 的边界**：只保存用户选定的范围，**永不自动运行**、默认不存整段对话（`save/SKILL.md` 第一段）。
- **hot.md**：最近上下文缓存，硬上限 500 词 / 32 KiB，每次 save 和 ingest 都要刷新。SessionStart 注入**默认关闭**，要设 `CLAUDE_OBSIDIAN_SESSION_CONTEXT=1` 才会注入。
- **跨项目**：vault 按 `--vault` → `CLAUDE_OBSIDIAN_VAULT` → 最近的 `.claude-obsidian.json` 的顺序解析，找不到就直接报错（fail closed）。

**不适合的**
- **lint 只做确定性检查**：死链、孤儿页、frontmatter、空章节、过期 index、账本合规。skill 明文禁止声称做过语义矛盾分析（`wiki-lint/SKILL.md`）。PCKS 想要的"矛盾、过期、建议升级"它都没有。
- **太重**：2.3 万行内核、15 个 skill、事务协议、地址分配器、BM25、Ollama 等。一次 save 要拼 bundle、算哈希、过两道门，对"解决完 bug 一句话沉淀"这个场景来说摩擦太大。
- **Stop hook 只报告事务锁和恢复状态**（`hook_adapter.py:240` `stop_status`），不做"本次有 N 条可沉淀"的提示。
- **上游变动频繁**（10 月刚从 2.x 升到 3.0，期间做过命名空间迁移），fork 后跟进的成本高。

### 2.3 karpathy-llm-wiki（最贴近原文、最轻）

- **一个 SKILL.md 就是 schema 层**，加上 4 个模板和 1 个校验脚本。核心规则写得非常干净，值得直接拿来做骨架：
  - **Grounding Invariant**：wiki 里所有承重事实（数字、日期、直接引用）必须在该页 `Raw:` 字段链接的 raw 文件里**逐字存在**。编译时"先定位再写"，lint 时由 `scripts/check_evidence.py` 用 grep 机械校验。
  - **Triage 四种处置**：New / Update / Disputed / No material。No material 只记 log 不出页，"不要从单薄的来源硬挤出一篇文章"。
  - **Cascade Updates**：不能只信 index，要全文搜实体和别名，更新所有受影响的页面。
  - **Status 块**：旧结论不静默改写，标 `Outdated (日期)` 或 `Disputed`，并保留原文。
  - **lint 分三档权限**：Safe Fixes 自动修（index 一致性、唯一可解析的断链）；Mechanical Reports 只报告（证据校验）；Judgment Reports 只报告（矛盾、过期、缺页概念、孤儿页、需要刷新的归档页）。
  - **query 不写文件**，用户明确要求归档时才回写，归档页"永远新建、不合并"，index 摘要加 `[Archived]` 前缀。
  - **Research 模式**要求刻意搜索反方证据（失败、批评、复现失败）。
- **不足**：只有一个 skill；只面向外部资料；没有 inbox、没有 promote、没有 hook；wiki 只允许一层 topic 目录；不用 wikilink（用相对 markdown 链接——Obsidian 也能解析，但图谱体验稍差）。

### 2.4 llm_wiki（nashsu，子代理审查，关键点已抽查）

- Tauri 2 + React 19 桌面应用；ingest 和 lint 写在前端 TS 里，本地 HTTP API 和 MCP 都要求桌面 App 在运行，**不能 headless**。许可证实际是 **GPLv3**，prompt 原文不能照搬，只能借鉴思路后自己重写。
- 值得借鉴的设计：
  1. **两段式 ingest**：先分析（每个候选输出 `Page-worthy: yes/no` 和理由，命名优先沿用 index 已有标题），再生成。
  2. **合并时代码管 frontmatter**：sources/tags/related 取并集，type/title/created 锁定；LLM 合并后正文缩水超过 30% 直接拒绝。
  3. **index、overview 由代码追加维护**，不交给 LLM 写。
  4. **补链接时 LLM 只返回"术语→目标"的 JSON**，替换由代码完成，模型不重写正文。
  5. **矛盾和同义页去重进 review 队列**，人确认后才合并。
  6. **lint 分两层**：确定性结构检查 + LLM 语义检查。
- 不适合：桌面进程依赖、LanceDB、JSON 状态文件（不适合放进 git 和 Obsidian）、query 回写不经合并、引用只到页面级。

### 2.5 所有实现共同的空白——正好是 PCKS 的核心

1. **都是"读资料"型**：输入是文章、论文、网页。没有一个实现针对"编码会话里产生的经验"——bug 的症状→原因→解法→适用版本、技术决策的取舍、Codex 执行中的教训。
2. **没有 promote**：没有任何实现把知识升级成规则、Skill 或 lint 规则。知识停在"查得到"。
3. **没有和开发工作流集成**：没有在拆需求前自动查、没有从执行器回流经验。
4. **lint 要么只做确定性检查（claude-obsidian），要么全靠 LLM 判断（karpathy-llm-wiki 的 Judgment 档）**。llm_wiki 的两层做法最合理。

## 3. 自有插件扩展点（子代理盘点 + 关键处抽查）

> 版本以 git tag 为准：spec-guard v0.86.7、delegate v0.8.6、tier-guard v0.2.9、agent-relay v0.9.5。

### 3.1 启动提示词里的描述，有几项实际不存在 ⚠️

| 描述 | 实际（已抽查） |
|---|---|
| Harness 治理层 | **没有实体**。只在 plugin-ecosystem 一份自动 PR 系统设计草稿里作为"未来接入点"出现 |
| SHA256 漂移检测 | **不存在**。`~/.claude/hooks`、`~/.claude/scripts` 里 grep 不到 |
| eslint-plugin-boundaries | **不存在**。haigeerlab 下没有任何 package.json 或 eslint 配置用到它 |
| skills-local / skills 双轨 | **不是实现**。全局 CLAUDE.md 写明 `~/.claude/skills-local/` 是"死目录"，故意不启用 |

**影响**：构想里 `/kb promote` 的落点"Harness 的 skills-local、CLAUDE.md、eslint 规则"有两个不存在。Phase 1 必须先把 promote 的落点重新定下来，MVP 也不能依赖 Harness。

### 3.2 真实存在的扩展点

| 插件 | 能挂的点 | kb 的用法 |
|---|---|---|
| **spec-guard** | ① 能力图模块表只校验前三列（`hooks/capability_map.py:116`），后面可以加列；也可以加一个独立的 `## 已知坑与历史决策` 小节（不在严格解析范围内）② `.agent/config.json` 的未知键会被保留 ③ `interface.json` 发布了 `map_view.py --json` 的只读契约 | 拆需求前"先查 kb"**没有可配置的插入点**，流程写在 `references/workflow-checkpoints.md` 的文字规则里。要挂上去就得改 spec-guard（在"需求确认"一节加一句"装了 kb 就先 `/kb ask`"） |
| **delegate** | ① `run_state.py:113` 的 `build_result` 生成 JSON 结果文件（`schema: 1`，含 `answer.path`），stdout 打印 `delegate: result=<路径>` ② `--rules-file`（最多 16 KiB，原样放在 preamble 之后）③ Git 验收块是纯文本（`codex-exec.sh:324`） | **lessons 回流**：kb 不必改 delegate，自己读结果文件和答复正文去抽取即可（零耦合）。**反向注入**：用 `--rules-file` 把相关坑喂给 Codex。注意结果文件放在临时目录、只保留最近 50 组 |
| **tier-guard** | `decisions.jsonl`（追加写入、权限 0600）；出厂 mode=off 时不记日志；prompt 只存长度和哈希；SEAMS S11 已明确拒绝提供对外查询接口 | 对 kb 价值很低。"用运行日志校验流程"（第 11 题）不能指望它 |
| **agent-relay** | 点对点会话信箱；没有 topic、没有订阅；生态规则禁止群发 | **不适合当事件总线**。插件之间传数据走文件约定或对方的 `--json` 输出 |

### 3.3 生态约定（必须遵守）

- `plugin-ecosystem/RULES.md`：**插件之间接口、契约、依赖方向的改动，必须经总负责人出方案、由你批准**；新增接缝先登记到 `SEAMS.md`。
- 依赖方式全部是**运行时探测的可选依赖**。可以直接照抄的先例是 spec-guard → agent-relay（`hooks/agent_relay_probe.py`）：只读对方的 `interface.json` 并卡版本范围，状态分 ready / not-installed / incompatible / unknown，没装就打印一句提示，不让任何命令失败。
- 所以 kb 应该：发布自己的 `interface.json`（把 `kb ask --json` 写成契约）；别的插件自己探测 kb；kb 只读别人已公开的产物。这样天然满足"kb 是可选依赖、不反向耦合"。

## 4. 哪些复用、哪些自己写

| 部分 | 来源 | 方式 |
|---|---|---|
| ingest 主流程：Triage 四种处置、Grounding Invariant、Cascade、Status 块、log 前缀格式 | karpathy-llm-wiki（MIT） | **改写复用**：照搬结构，改成中文、加入经验类页面 |
| `check_evidence.py` 证据校验 | karpathy-llm-wiki（MIT） | **直接 vendor**（保留许可证和出处），按我们的页面字段改 |
| inbox 只追加 / raw 只创建 / hot.md 上限 / save 不自动运行 / 按来源类型分析 / vault 解析顺序 | claude-obsidian（MIT） | **借鉴设计**，不搬事务内核 |
| SHA-256 前置条件防并发覆盖 | claude-obsidian | **简化借鉴**：只在"会话里两个 agent 同时写 wiki"时需要，MVP 先用 git 兜底，按需再加 |
| Page-worthy 门槛、代码维护 index、frontmatter 并集 + 缩水检查、补链接只返回映射、两层 lint、review 队列 | llm_wiki（GPLv3） | **只借思路、自己重写**，不复制任何原文 |
| 经验类页面模板（pitfall / decision / pattern / project） | 无 | **自己写** |
| `/kb promote` 及其落点 | 无 | **自己写**（落点先在 Phase 1 定） |
| inbox 采集的 hook、spec-guard / delegate 集成、`interface.json` | 无 | **自己写**，按生态约定走总负责人 |
| 中文语境下的检索（同义词、中英混排术语） | 无 | **自己写**：index + `rg` 起步，超过阈值再上 qmd |

## 5. 基座推荐

**推荐：自研一个薄的 `kb` 插件（Claude Code 插件 + Codex 共用的 Agent Skills），以 karpathy-llm-wiki 为 prompt 骨架，选择性吸收 claude-obsidian 和 llm_wiki 的设计。不 fork 任何仓库。**

理由：

1. **输入类型不同，fork 了也要大改。** 所有实现都是"读资料"型；PCKS 的主要输入是工作经验。页面类型、ingest 的分析维度、触发方式都要重写，fork 留下的大部分都会是用不上的部分。
2. **claude-obsidian 太重，而且上游变动快。** 2.3 万行内核和事务协议能保证正确性，但"一句话沉淀"的摩擦会直接违背"整理太累坚持不下来"这个需求本身。它的价值在设计思想，不在代码。
3. **karpathy-llm-wiki 小而准、MIT、已兼容 Codex**，规则写得最接近原文，`check_evidence.py` 带测试可以直接用。拿它当骨架，新增量在可控范围。
4. **确定性部分写成脚本，判断部分交给 LLM。** 这是 llm_wiki 验证过的做法，也是你 constraint = quality 的落地方式：index / log / 断链 / 证据校验 / frontmatter 合并由脚本保证，LLM 只做分类、综合和语义判断。
5. **集成方式由生态规则决定**：kb 只读别人公开的产物，自己发布 `interface.json`；需要改 spec-guard 的那一句提醒，走总负责人。

**实跑验证已完成，见第 7 节。推荐不变，但根据实跑结果补了三条设计输入。**

## 6. 带入 Phase 1 的问题与修正

1. **promote 的落点要重定**：Harness 的 SHA256 漂移检测、eslint-boundaries、skills-local 都不存在。可选落点只剩：项目 CLAUDE.md/AGENTS.md、`~/.claude/skills/`（个人 skill）、插件内 skill、delegate 的 `--rules-file`、真实项目的 eslint 配置。
2. **第 11 题（用运行日志自进化）**：tier-guard 的日志帮不上；可行的数据源是 kb 自己的 `log.md` 和 lint 报告。
3. **第 6 题（集成接口）**：调研已基本给出答案——文件约定 + `interface.json` + 运行时探测，不用 agent-relay、不加 hook 依赖；改 spec-guard 走总负责人。
4. **会话结束 hook**：claude-obsidian 的 Stop hook 只报告事务状态；"检测到解决了问题就提示"没有先例，需要在 Phase 1 定打扰程度。
5. **语言**：现有实现的 prompt 都是英文，我们要定 SCHEMA 和页面的语言规范（第 9 题）。
6. **规模阈值**：原文给出"约 100 个源、几百页内只靠 index"的经验值，可以作为第 7 题的起点；qmd 是之后的升级路径。

## 7. 实跑对比（2026-11-19）

### 7.1 方法

- **素材**：三段真实经验，取自 `~/.claude/CLAUDE.md` 里记录的过往会话。
  - s1：从 agent 里调 `codex exec` 的三个坑，坑类经验。
  - s2：2026-08-28 的决策"机械活派给子代理便宜得多"。
  - s3：2026-10-06 的实测，推翻了 s2。用来测矛盾和过期的处理。
- **执行**：由我严格按各自的 SKILL.md 逐步执行。两边的确定性脚本（claude-obsidian 的 CLI、karpathy 的 `check_evidence.py`）照实运行，环境在 scratchpad 的临时目录里。
- **查询**：从另一个项目目录（`tab-leader`）发起"派活给子代理或 Codex 要注意什么，省钱吗？"。
- **未实测**：没有真实调起 Codex 读 skill。派 Codex 需要用户先同意，这一项留到 Phase 4 做。

### 7.2 结果

| 维度 | claude-obsidian 3.0.1 | karpathy-llm-wiki |
|---|---|---|
| 初始化 | `init` 预览 → 带批准哈希 apply，2 条命令。生成 14 个文件（含 `.obsidian/` 配置和两本账本） | 第一次 ingest 时顺手建出 `raw/`、`wiki/`、index、log |
| save（s1） | 要手写事务 bundle：笔记、index、log、hot 4 个写入，每个都带 SHA-256 前置条件。**inspect 2 轮才通过**：第 1 轮被门禁拦下，原因是 index 里的链接必须带路径 | 没有 save 操作，素材走 ingest；1 次 ingest，3 个文件 |
| 第一次 ingest（s2） | 7 个写入：raw、页面、两本账本、index、log、hot。**inspect 3 轮才通过，共被拦 7 处**：锚点格式、source ID 规则、字段名、日期格式。账本字段在 skill 文档里没有写全，**只能去读 `ledgers.py` 的源码** | 1 次写入就完成：raw、页面、index、log，另外给已有页面补一条 See Also |
| 矛盾处理（s3） | 2 轮通过：`supersedes` 只接受单个 ID。最终状态很好：旧结论在账本里是 `deprecated` 并带 `contradicts` 证据，新结论记了 `supersedes`，**机器可读** | 1 次写入完成。旧结论保留原文，下面加 `Status: Outdated (2026-10-06)` 块，新增"现行判据"一节，index 摘要同步更新。**只有人能读懂，机器读不出** |
| lint | 确定性检查发现 2 处"链接指向隐藏目录 `.raw/`"：raw 在 Obsidian 图谱里看不到，这是设计层面的摩擦。**完全没有提示有一条结论已被推翻**，因为它不做语义检查 | 证据校验 0 问题。故意植入 2 个错误数字后**只抓到 1 个**，漏掉的那个在 Status 块里：`check_evidence.py:225` 会跳过整个 Status 块。**更正后的结论恰恰是最需要核对的部分，却不在校验范围内** |
| 跨项目查询 | 不设环境变量会直接报错 `VAULT_NOT_FOUND`；设了 `CLAUDE_OBSIDIAN_VAULT` 就能正常找到知识库 | **没有跨项目机制**，默认知识库就在当前项目根目录下 |
| 查询命中 | 读 hot、index、2 页和 claim ledger，约 4.9KB，命中正确，还能按 `assessment` 过滤掉 deprecated 的结论 | 读 index、全文搜同义词、2 页，约 3.0KB，命中正确 |
| 其他问题 | 日期按 UTC 写，本地已经是 11-19，它写成 11-18；账本还要求 `generated_at` 不晚于审计日期，东八区凌晨很容易撞上 | 无 |

### 7.3 结论

1. **推荐不变：自研薄插件，用 karpathy-llm-wiki 做骨架。** 在 claude-obsidian 里，一次 ingest 要写 7 个文件、手工拼 bundle、反复过校验，我照着文档做第一次就被拦了 7 处。把它放在"解决完 bug 一句话沉淀"的路径上，摩擦大到会直接劝退使用。karpathy 的写入路径几乎没有摩擦。
2. **但 claude-obsidian 有两点实跑证明有价值，要吸收（做轻量版）：**
   - **结论状态要机器可读。** 只靠 Status 块的文字，ask 时没法由程序过滤掉被推翻的结论。建议在页面 frontmatter 或段落块 ID 上记 `status: current / outdated / disputed` 和 `superseded_by`，由脚本校验，不引入两本 JSON 账本。
   - **写入前要有校验门禁。** 门禁拦下的错误都是真错误（链接没带路径、锚点不存在）。建议做成"写完由脚本校验，不通过就报错"，不要求事先拼 bundle、算哈希。
3. **karpathy 的证据校验要补一个洞**：Status 块和"现行判据"里的数字也要校验。我们 vendor 这个脚本的时候改掉第 225 行的跳过逻辑，并补一条测试。
4. **跨项目是硬需求，两边的现成方案都不够。** karpathy 根本没有；claude-obsidian 靠环境变量。我们的 kb 应该固定一个知识库位置（例如 `~/Documents/haigeerlab/kb`），由插件配置解析，在任何项目里都能 `/kb ask`。
5. **raw 不要放在隐藏目录里**，否则 Obsidian 图谱和 lint 都会报链接问题。karpathy 用的 `raw/` 是对的。
6. **日期统一用本地时区**（Asia/Shanghai），避免 UTC 跨日带来的错位。
