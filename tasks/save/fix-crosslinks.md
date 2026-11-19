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

## 变更记录

- 2026-11-19 初稿。
