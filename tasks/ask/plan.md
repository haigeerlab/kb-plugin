<!-- spec-guard: review approved -->

# Plan: ask

> Spec：[spec/ask.md](../../spec/ask.md)（已批准）

## 执行方式

和 save 一样：检索脚本和测试一次性派给 Codex（`--write`，任务文本从文件读入）；SKILL.md 由主会话并行编写；三项真实环境验证（AC5–AC7）是 gate。

## 任务

### T0 修复模板日期（主会话，vault-contract 范围内的修正）
- 根因：`init.py:20` 把模板复制进知识库时，把 `{{date}}` 替换成了当天日期，于是知识库 `templates/*.md` 的日期被写死了。
- 改法：复制时把 `{{date}}` 替换成 `YYYY-MM-DD` 占位符（和 save 的 SKILL.md 写法一致）；补 1 条测试（init 后的模板里不含具体日期）；在 vault-contract 的 Spec 变更记录里加一行。
- 同时修复你真实知识库里的 5 个模板：把其中写死的 `created: 2026-11-19`、`updated: 2026-11-19` 改回 `YYYY-MM-DD`，跑 `kb check` 后在知识库里本地提交。`templates/` 不在 inbox 和 raw 下，不受 immutable 约束。
- 检查点：report

### T1 检索脚本（派 Codex，--write，期限 1500 秒，后台）
- 内容：
  - `kblib/ask.py`（多词匹配、区域标注、整页 superseded、排序、limit 与 truncated、命中行截断）；
  - `kb.py ask search`；
  - `interface.json` 与 `references/interface.md`（契约 1.0）；
  - `check-manifests.py` 增加对 interface.json 的校验；
  - `tests/test_ask.py`（覆盖 Spec 的 Testing Strategy，含 schema 断言和只读断言）；
  - README 更新。
- 约束：不碰 `skills/ask/`；不动 vendor；不碰真实的知识库和配置；不联网；不提交。
- 检查点：report

### T2 SKILL.md（主会话，与 T1 并行）
- `skills/ask/SKILL.md`：内联根目录解析片段（由脚本注入）；写清抽词 → search → 读候选全文 → 只基于 current 区域回答并附链接 → outdated 作为历史提及 → disputed 摆出各方说法 → 查不到就明说并列出搜过的词 → 模型自己的知识要单独标注 → 不写文件。
- 检查点：report

### T3 主会话复核与提交
- 逐条核验 AC1–AC4。对抗抽查：
  1. 只在 `[!outdated]` 块里出现的词，命中区域必须是 `outdated`，并且排在 current 命中的页面后面；
  2. `status: superseded` 的页面，全部命中都是 `outdated`，并带 `superseded_by`；
  3. 代码块里的命中，区域按所在块判定；
  4. 正则特殊字符（如 `a.b`、`(x)`）当作普通字面量匹配，不报错；
  5. 搜索前后知识库的 git 状态不变；
  6. 没有命中时退出码为 1，JSON 合法。
- 通读 `ask.py`。通过后提交，刷新 Codex 缓存。
- 检查点：report

### T4 真实环境验证（gate，模块最终验收）
- 停下来问你后执行：
  - **AC5**：在 tab-leader 用 `claude -p` 新开进程，问"Codex 里改了插件的 skill 为什么不生效？"；
  - **AC6**：复制 dispatch 样例到临时目录并 git 提交，用 `KB_CONFIG` 指向它，`claude -p` 问"把机械活派给子代理省钱吗？"；
  - **AC7**：delegate 只读派 Codex，在 tab-leader 问 AC5 那个问题。
- 三项的回答原文都摘录进验收记录。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| 区域判定和 markdown.py 的标注块解析不一致 | ask.py 复用 `markdown.callouts`，不另写解析器 |
| 模型回答时仍然引用 outdated 内容当作结论 | SKILL.md 把规矩写在最前；AC6 实测 |
| `claude -p` 在 tab-leader 受该项目自己的规则干扰（之前出现过 module-crew 提醒） | 只看回答的主体部分；干扰内容如实记录，不算失败 |

## 变更记录

- 2026-11-19 初稿。
