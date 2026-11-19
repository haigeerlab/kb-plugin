<!-- spec-guard: review approved -->

# Plan: save

> Spec：[spec/save.md](../../spec/save.md)（已批准）

## 执行方式

- 脚本和测试一次性派给 Codex（`--write`）。任务文本先写进文件再读入，避开上次撞到的安全检查。
- SKILL.md 由主会话来写（Spec 假设 9），和 Codex 的派单并行进行：Codex 在后台跑，主会话同时写 SKILL.md，两边改的文件互不重叠。
- 主会话负责复核、对抗抽查、提交。两次真实环境验证（AC5、AC6）是 gate。

## 任务

### T1 save 脚本（派 Codex，--write，期限 1800 秒，后台）
- 内容：
  - `kblib/save.py`：草稿目录遍历、路径白名单、叠加到临时副本、脱敏（先替换代号）、全量 `kb check`、diff 生成、指纹、原子写入与回滚、git commit；
  - `kb.py` 新增 `save preview` / `save apply` 子命令；
  - `tests/test_save.py`，覆盖 Spec Testing Strategy 的全部内容（含端到端连续三次 save）；
  - README 中把 `/kb:save` 标为已实现，写明流程和退出码。
- 约束：不要创建或修改 `plugins/kb/skills/save/`（由主会话负责）；不动 vendor；不碰真实的知识库和 `~/.config/kb`；不联网；不提交。
- 验收：测试全绿；Git 验收块范围符合预期。
- 检查点：report

### T2 SKILL.md（主会话，与 T1 并行）
- `plugins/kb/skills/save/SKILL.md`：内联根目录解析片段；写清范围确认、inbox 提炼规则（承重事实逐字摘录、来源字段）、检索步骤（index → 全文搜索含同义词和中英文术语 → 读候选页面）、四种处置及其写法、页面模板位置、index 和 log 的格式、preview → 原样展示 → 明确确认 → apply → 报告提交号。敏感内容引用 SCHEMA，不重复写。
- 验收：片段一致性测试通过；frontmatter 只有 name 和 description。
- 检查点：report

### T3 主会话复核与提交
- 对照 AC1–AC4、AC7 逐条核验。对抗抽查：
  1. 草稿里改一个已有的 inbox 文件，必须被拒绝；
  2. 草稿里放 2 个 inbox 文件，必须被拒绝；
  3. preview 之后在知识库里提交一个新文件，apply 必须返回 3；
  4. 草稿里放一个假密钥，必须报 `redaction`，不写入；
  5. 草稿通过了，但 index 里漏了新页面，必须报 `index`；
  6. 模拟 apply 写到一半失败，知识库必须完整回滚。
- 通读 `save.py`。通过后本地提交。
- 检查点：report

### T4 真实沉淀第一条知识（gate，AC5）
- 停下来问你后执行：在本会话里按 SKILL.md 走一遍 `/kb:save`，主题是"Codex 插件缓存的刷新"这个坑。给你看预览，你确认后 apply。完成后 `kb check` 为 0 问题，知识库多 1 个提交。
- 先刷新 Codex 缓存（`codex plugin add kb@kb-marketplace`），为 T5 做准备。
- 检查点：gate

### T5 Codex 跨宿主验证（gate，AC6，模块最终验收）
- 停下来问你后执行：通过 delegate 只读派单，让 Codex 在 tab-leader 目录按 `kb:save` 处理一段描述同一个坑的文字，只做到 preview，不 apply。预期结果是 Codex 找到 T4 写入的页面，把处置判为"并入"或"没有新内容"。
- 只读沙箱下 Codex 不能往系统临时目录写草稿：如果 preview 因此跑不了，就退而验证"检索和处置判断"这一步，在验收记录里如实写明。
- 检查点：gate（模块最终验收）

## 风险

| 风险 | 应对 |
|---|---|
| 临时副本上跑 `kb check` 的 immutable 检查需要 git 历史 | 副本用 `git worktree` 或 clone 方式创建，保留历史；测试覆盖 |
| 指纹漏算某种变化，导致覆盖别人的改动 | 指纹 = HEAD + `git status --porcelain` + 草稿内容哈希；测试覆盖三种变化 |
| SKILL.md 写得太长，模型执行时漏步骤 | 用编号步骤，关键约束放在最前；T4 实跑检验 |
| Codex 只读沙箱下写不了草稿 | T5 已写明退路 |

## 变更记录

- 2026-11-19 初稿。
