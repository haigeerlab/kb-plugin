<!-- spec-guard: review approved -->

# Plan: inbox-compile

> Spec：[spec/inbox-compile.md](../../spec/inbox-compile.md)（已批准）

## 执行方式

和前几个模块一样。多一个前置任务：会话记录的样例由主会话构造。Codex 需要知道真实的 jsonl 结构，但你的真实会话内容不能交给它，所以只提取结构、填入虚构内容。

## 任务

### T0 会话记录 fixture（主会话）
- 以一份本机真实会话记录为参照，只取结构，构造 `tests/fixtures/transcripts/basic.jsonl`。覆盖的记录类型：
  - 用户输入（`message.content` 为字符串，`isMeta=false`）；
  - 系统注入（`isMeta=true`，字符串或 text 块）；
  - 工具结果（`content` 为 `tool_result` 块，带 `toolUseResult`）；
  - assistant 的 `text` / `tool_use` / `thinking` 块；
  - 子代理消息（`isSidechain=true`）；
  - `attachment`、`queue-operation` 记录；
  - 一行损坏的 JSON；
  - 正文里含 `<system-reminder>` 的用户消息。
- 内容全部虚构；假密钥只在测试运行时拼接，不写进 fixture。
- 同时写一份 `tests/fixtures/transcripts/README.md`，说明每种记录是否保留。
- 检查点：report

### T1 实现（派 Codex，--write，期限 2400 秒，后台）
- 内容：
  - `candidates.py`：队列、去重、状态流转、清单（复用 lint 的积压判定）、过期判定、提取与打码、截断；
  - `compile.py`；
  - `writer.py` 支持 `compile`；
  - `kb.py candidates add|list|show|mark`、`compile preview|apply`；
  - 测试：`test_candidates.py`、`test_compile.py`，含端到端；
  - README。
- 提取规则：
  - **保留**：用户输入的字符串（去掉 `<system-reminder>…</system-reminder>` 片段），以及 assistant 的 `text` 块；
  - **跳过**：其他所有内容。
- 约束：不碰 `skills/`；save、lint、commit-pending 的原有测试不改且必须全绿；不碰真实的知识库、配置和 `~/.local/state/kb`；不联网；不提交。
- 检查点：report

### T2 SKILL.md（主会话，与 T1 并行）
- 新建 `skills/compile/SKILL.md`，按三步流程写：清单 → 你挑选 → 批量预览 → 你确认 → 逐条写入并在失败时停下。两类来源各自的写法也要写清；提交失败时走 `commit-pending` 的规则。
- 检查点：report

### T3 主会话复核与提交
- 逐条核验 AC1–AC5，并做对抗抽查：
  1. 在 fixture 里的工具输出中放一段运行时拼接的假密钥，`candidates show` 的输出里不能出现它；
  2. assistant 的 `thinking` 和子代理消息不能出现在输出里；
  3. 同一个 `session_id` 入队两次，只保留一条；
  4. 会话文件被删除后，`list` 把对应候选转为 `expired`；
  5. compile 草稿里放 2 个 inbox 文件时被拒绝；放 0 个 inbox、只引用已有 inbox 时通过；
  6. `git diff` 确认 save、lint、commit-pending 的测试文件没有改动。
- 通读 `candidates.py`、`compile.py`；通过后提交，并刷新 Codex 缓存。
- 检查点：report

### T4 真实环境验证（gate，模块最终验收）
- 停下来问你后执行：
  - **AC6**：列出你最近 10 个会话的项目名、时间和第一句话（前 30 字）。**你挑一个**后用 `candidates add` 入队，在本会话里走 `/kb:compile`：第一步清单你决定编译还是丢弃；如果编译，第二步你确认，第三步写入，`kb check` 0 问题。
  - **AC7**：delegate 只读派 Codex 跑第一步（清单）。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| 会话记录格式随 Claude Code 版本变化 | 提取只依赖 `type`、`isMeta`、`isSidechain`、`message.content` 几个字段；遇到无法识别的记录跳过并计数，在输出末尾报告"跳过 N 条无法识别的记录" |
| 会话很长，提取后仍然超过上限 | 默认截断到 4 万字，保留**结尾**部分（问题通常在后段才解决），并标注截断 |
| 修改 writer 影响 save、lint | 原有测试不改且全绿；T3 抽查 6 |

## 变更记录

- 2026-11-19 初稿。
