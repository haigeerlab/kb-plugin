# Todo: inbox-compile

- [x] T0 会话记录 fixture，主会话（report）— `783ca74`；按真实结构构造、内容虚构，覆盖 8 类记录和损坏行，每类该跳过的内容都带 `*-MARKER`
- [x] T1 实现，派 Codex --write（report）— run `20261119182917.83257`，status=done，`--check` 通过；Git 验收块：基线 `783ca74`，新增 candidates.py、compile.py、两个测试文件，修改 kb.py、README、lint.py（把积压判定抽成共享的 `inbox_backlog`）、save.py（草稿读取加 `operation` 参数，compile 允许 0 或 1 个 inbox）、writer.py（待提交记录允许 compile，1 行）；旧测试和 fixture 都没有改动
- [x] T2 compile SKILL.md，主会话（report）— 127 行，四条硬约束放在最前；同一批多项会共同修改 index 和 log，所以第二项起在前一项写入之后重新生成 index 和 log 并重新 preview；页面内容和已确认版本不一致时，停下来重新确认
- [x] T3 主会话复核与对抗抽查，并提交（report）
  - AC1：unittest 共 233 项全部通过（新增 30 项）
  - 抽查 1：fixture 工具输出里换入运行时拼接的假 token，`candidates show` 输出中没有该 token，也没有工具输出内容 ✓
  - 抽查 2：THINKING、SIDECHAIN、META、META2、ATTACH、REMINDER、TOOLUSE 标记都没有出现；用户输入和 assistant 正文保留 ✓
  - 抽查 3：同一个 session_id 入队两次，队列里只有 1 行 ✓
  - 抽查 4：会话文件删除后，list 把候选转为 expired 并写回 ✓
  - 抽查 5：compile 草稿 0 个新 inbox（引用已有积压）、1 个新 inbox 都通过；2 个被拒绝 ✓
  - 抽查 6：test_save、test_lint、test_commit_pending 的 diff 为 0 行 ✓
  - AC2–AC5：由测试和上面的抽查覆盖；SKILL 两次决定都要等用户明确回复
- [ ] T4 真实环境验证 AC6、AC7（gate，模块最终验收）
