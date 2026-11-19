<!-- spec-guard: review approved -->

# Plan: lint

> Spec：[spec/lint.md](../../spec/lint.md)（已批准）

## 执行方式

和前几个模块一样：重构和实现一次性派给 Codex（`--write`，任务文本从文件读入）；两份 SKILL.md 由主会话负责（新建 lint，修改 save），与 Codex 并行；两项真实环境验证（AC6、AC7）是 gate。

## 任务

### T1 共享写入路径重构 + lint 实现（派 Codex，--write，期限 2400 秒，后台）
- 内容：
  - 从 `save.py` 抽出 `writer.py`（叠加校验、指纹、diff、原子写入与回滚、提交），save 改为调用它，行为不变；
  - `lint.py`（孤儿页、疑似过期、inbox 积压、规模指标、分组、三类安全修复的草稿生成）；
  - `kb.py lint` / `lint fix preview|apply`；
  - `tests/test_lint.py`；
  - README 更新。
- 约束：
  - 不碰 `skills/`；
  - save 原有测试一条都不改，并且必须全绿（如确实需要改测试，必须停下来报告原因，不能自行修改）；
  - 不动 vendor；不碰真实的知识库和配置；不联网；不提交。
- 检查点：report

### T2 SKILL.md（主会话，与 T1 并行）
- 新建 `skills/lint/SKILL.md`：运行 lint → 按分组解释（区分事实和建议）→ 有可修复项时给预览 → 你明确确认后执行 apply → 报告提交号；不可修复的项只给建议。
- 修改 `skills/save/SKILL.md`：判为"没有新内容"时，log 正文必须写出 inbox 路径；同时在 save 的 Spec 变更记录里补一行。
- 检查点：report

### T3 主会话复核与提交
- 逐条核验 AC1–AC5、AC8。对抗抽查：
  1. **重构等价**：`git diff` 确认 `tests/test_save.py` 没有被改动，save 测试全部通过；
  2. 断链有两个同名候选时，`lint fix` 不修，只报告；
  3. 安全修复后 `kb check` 为 0 问题，提交里同时包含修复和 log 条目；
  4. 不带 fix 的 `lint` 前后，git 状态不变；
  5. 写了 inbox 路径的"没有新内容"log 条目，对应的 inbox 不算积压；没写路径的仍然算；
  6. project 页不报孤儿页；只有 index 链接到的页面要报孤儿页。
- 通读 `writer.py` 和 `lint.py`。通过后提交，刷新 Codex 缓存。
- 检查点：report

### T4 真实环境验证（gate，模块最终验收）
- 停下来问你后执行：
  - **AC6**：在你真实的知识库上跑 `/kb:lint`（Claude Code，`claude -p`），预期 check 级 0 问题，孤儿页提示 1 条；不执行 fix。
  - **AC7**：delegate 只读派 Codex 跑 `/kb:lint` 的报告部分，和 AC6 的结果对比。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| 重构改变了 save 的行为 | 约束里写死"不改 save 测试"；T3 抽查 1 |
| 孤儿页在知识库很小时产生大量提示，显得吵 | 只作为提示级、放在最后一组；数量写进报告摘要 |
| "疑似过期"阈值不合适 | 可通过 `--stale-days` 调整；Phase 6 试用后再定默认值 |

## 变更记录

- 2026-11-19 初稿。
