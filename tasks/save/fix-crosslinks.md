<!-- spec-guard: review approved -->
# Plan: save 修订——写页面时建立互链

> Spec：[spec/save.md](../../spec/save.md)「修订：写页面时建立互链」一节（待批准）

改动很小，都在主会话里做，不派 Codex。

## 任务

### X1 修改 save SKILL.md（主会话）
- 第 4 步：检索时列出相关页面（最多 3 篇，宁缺毋滥）。
- 第 6 步：本页末尾写 `## 相关`；每篇相关页复制进草稿，在它的 `## 相关` 里加一条指回本页的链接，刷新 `updated`，其余内容一字不改。
- 第 8 步：预览说明里要列出改了哪些相关页；没有相关页时写明"未发现相关页面"。
- 验收：片段一致性测试通过；全量测试通过。
- 检查点：report

### X2 存量补链（主会话，gate）
- 以 compile 操作（0 个新 inbox）给现有 6 篇补链，按我判断的相关关系：
  - `npm-staged-publish-404` ↔ `module-crew-tag-push-no-verify`：同一次 tab-leader 0.2.0 发版的两个坑；
  - `codex-plugin-cache-refresh` ↔ `codex-kb-git-sandbox-pending`：都是 Codex 插件开发、调试中遇到的宿主行为；
  - `git-temp-repo-identity` ↔ `codex-kb-git-sandbox-pending`：都是 kb 写入后 git 提交失败的原因和处理；
  - `pwa-display-mode-fullscreen`：没有相关页，保持不变。
- 给你看完整 diff 和指纹，你确认后 apply；然后 `kb check` 0 问题，lint 的孤儿页只剩 1 条。
- 检查点：gate

## 执行记录

- [x] X1 — `12a8d4c`：save SKILL 第 4 步列出相关页（最多 3 篇），第 6 步双向写 `## 相关`，相关页其余内容一字不改；第 8 步列出互链情况。片段一致性测试和全量测试都通过
- [x] X2（gate，用户 2026-11-19 确认写入）— 补链 preview 指纹 `1d4e1ad908771ce6`，5 篇页面末尾追加 `## 相关`，共 3 对相关关系；apply 后知识库提交 `a49e9c0`，`kb check` 0 问题，lint 孤儿页 6 → 1（只剩 PWA 一页，确实没有相关页）
  - 发现：这次提交的信息是 `compile: Codex 沙箱能写知识库却无法提交…`，应为 `compile: 补充页面互链`。原因是 compile 在 0 个新 inbox 时取第一个被修改 wiki 页的标题；只改已有页面的补链操作应改为取 log 新增条目的标题。没有改写已有提交，记为小修复项
- [ ] AC14 下一次真实的 save 或 compile 时，确认预览里出现 `## 相关` 或"未发现相关页面"（由用户触发，不阻塞）

## 变更记录

- 2026-11-19 初稿。
