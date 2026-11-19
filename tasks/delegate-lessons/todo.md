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
- [x] T4 真实 delegate 结果扫描与 compile（gate，用户 2026-11-20 批准执行）
  - T4 之前 hook 已在真实会话结束时自动扫描过一次（真实环境自动采集可用）
  - **发现 2 个真实格式问题（fixture 未覆盖）并修复**（`eaeb4f3`，先红后绿，全量 286 项通过）：① 只读 run 的 `changedFiles` 为 null，8 个被判"格式无效"；② 续跑 run 为 `kind: resume`，续跑到 done 的链会被漏收。修复后从真实 `delegate-scan.json` 删去 10 条错判记录重扫（已备份 `delegate-scan.json.bak-20261120`）
  - 最终：22 个真实结果，收集 18、跳过 4（2 条 needs-input 链的链头与 resume）
  - AC6：在本会话走 `/kb:compile` 清单，18 个 delegate 候选全是交付说明，用户选择全部丢弃（`candidates mark --status dropped`）；15 个会话候选不在本次范围，保持原样
  - `kb check` 0 问题；delegate 目录 128 个文件扫描前后哈希一致（不含 delegate 自己 hook 写的 detection.json）
  - 如实记录：本次 18 个候选没有一条可复用经验。"有失败命令"的信号被 TDD 红灯与 rg 无匹配（退出 1）污染，答复也都超过 200 字节，过滤几乎不起作用
- [ ] 延期：提升 delegate 候选质量（派单时让 Codex 在答复末尾固定输出"踩到的坑"一节，收集条件改为看该节是否存在）；恢复条件：用户决定做 delegate 提示词侧改动时（Spec 假设 5）

## 最终验收

- [x] 用户 2026-11-20 批准最终验收（Spec 未修改；T4 发现的两处真实格式问题已在 `eaeb4f3` 修复；候选质量改进保留为延期项）
