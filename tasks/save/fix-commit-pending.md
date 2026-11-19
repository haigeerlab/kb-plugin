<!-- spec-guard: review approved -->
# Plan: save 修订——提交失败后的待提交状态

> Spec：[spec/save.md](../../spec/save.md)「修订：提交失败后的待提交状态」一节（待批准）

## 任务

### F1 实现（派 Codex，--write，期限 1500 秒，后台）
- 内容：
  - writer.py：提交失败时写 `.kb-pending.json`；有待提交记录时 publish 拒绝并给出提示；
  - `kb.py commit-pending`；
  - `kb check` 和 lint 忽略 `.kb-pending.json`；
  - 测试覆盖 AC8–AC10；
  - README 补"提交失败怎么办"。
- 约束：不改 `skills/`；save、lint 原有测试不改且全绿；不碰真实知识库和配置；不联网；不提交。
- 检查点：report

### F2 SKILL.md（主会话，与 F1 并行）
- save、lint 两份 SKILL.md：apply 报"已记录待提交"时，把 `commit-pending` 命令原样告诉用户；禁止自己执行 git add、git commit 或改 `.git`。
- 检查点：report

### F3 主会话复核与提交
- 逐条核验 AC8–AC10。对抗抽查：
  1. 记录中的文件被改了一个字节，`commit-pending` 拒绝；
  2. 工作区多出一个记录以外的文件，拒绝；
  3. 记录被删掉，或者 JSON 损坏，退出 2，不崩溃；
  4. 成功后 `.kb-pending.json` 被删除，提交里只包含记录中的文件，不包含 `.kb-pending.json`。
- 通过后本地提交，刷新 Codex 缓存。
- 检查点：report

### F4 重跑 V4（gate，AC11）
- 停下来问你后执行：delegate 派 Codex 可写可续跑执行 save → 预览转给你确认 → 续跑 apply（预期提交失败并生成待提交记录）→ 在 Claude Code 里运行 `commit-pending` → `kb check` 0 问题。
- 检查点：gate

## 执行记录

- [x] F1 — run `20261119170832.47932`，status=done，`--check` 通过；Git 验收块：基线 `80b0ef9`，修改 writer.py（+123 行）、kb.py、vault.py、save.py、lint.py、README，新增 test_commit_pending.py（12 项）；test_save.py、test_lint.py 没有改动
- [x] F2 — save 和 lint 的 SKILL.md 各加 2 条：遇到"已记录待提交"时，把命令原样转告用户；遇到"有待提交记录"时，先请用户提交。禁止自己执行 git add/commit，禁止改 `.git` 或 `.kb-pending.json`
- [x] F3 — unittest 共 203 项全部通过。用把临时知识库 `.git` 设成只读的方式真实触发提交失败：AC8 apply 退出 1，提示含 commit-pending，记录 4 个文件，HEAD 不变；AC10 有记录时 preview 被拒绝；抽查 1 改一个字节 → 拒绝，记录保留；抽查 2 多出记录外的文件 → 拒绝；抽查 3 JSON 损坏 / 记录缺失 → 退出 2，没有崩溃；抽查 4 成功 → `save: 沙箱禁止写 git` 只包含 4 个记录文件，记录已删除，check 0，工作区干净
- [ ] F4 重跑 V4（gate，AC11）

## 变更记录

- 2026-11-19 初稿。
