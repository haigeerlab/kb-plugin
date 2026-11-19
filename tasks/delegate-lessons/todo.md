# Todo: delegate-lessons

- [x] T0 delegate 结果 fixture，主会话（report）— `9f15ede`：11 组（收 5、跳过 6），结构取自真实结果文件，内容虚构
- [x] T1 实现，派 Codex --write（report）— run `20261119235426.24829`，status=done；Git 验收块：基线 `9f15ede`，新增 delegate_lessons.py、test_delegate_lessons.py（21 项），修改 candidates、capture、config、kb.py、README；未碰 skills、清单、hooks.json、原有测试；未提交。**`--check` 失败（29 项）**，Codex 自述全绿——它的沙箱 TMPDIR 下 delegate 目录为空，见 T3
- [x] T2 compile SKILL 与 inbox-compile 变更记录，主会话（report）— `6818a21`
- [x] T3 主会话复核与 6 项对抗抽查，并提交（report）
  - 通读 delegate_lessons.py 及 candidates、capture 改动，与 Spec 一致
  - fixture 首扫：收 1001、1003、1006、1007、1008，跳过 6 个，与 README 期望一致
  - 抽查 1 只读：扫描前后 fixture 目录哈希不变；抽查 2 增量：再扫处理 0；抽查 3：25 个新结果分 20＋5 两次处理
  - 抽查 4：hooks.json 原始命令、200 文件目录，正常与损坏输入均退出 0、无输出，0.12 秒和 0.10 秒
  - 抽查 5：运行时拼接的假密钥在 `candidates show` 中无明文；抽查 6：原有测试零改动（Codex 交回时）
  - **偏离 Plan（用户 2026-11-20 批准）**：原有 `test_capture.py` 两处 env 只覆盖 KB_CONFIG、KB_STATE_DIR，hook 新增的扫描读了本机真实 delegate 目录，把真实 run 收进测试临时队列 → 29 项失败。只补隔离：两处 env 加 `KB_DELEGATE_DIR` 指向空临时目录，不改断言。补后在真实环境（不设 KB_DELEGATE_DIR）跑全量通过
- [ ] T4 真实 delegate 结果扫描与 compile（gate，模块最终验收）
