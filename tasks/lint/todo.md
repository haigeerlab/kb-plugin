# Todo: lint

- [x] T1 共享写入路径重构 + lint 实现，派 Codex --write（report）— run `20261119160844.4257`，status=done，`--check` 通过；Git 验收块：基线 `1e06284`，save.py 删掉约 240 行改为调用新的 writer.py（抽出 state、target_path、fingerprint、overlay_check、diff、atomic_write、commit、masked、empty_result，由 publish 编排），新增 lint.py、test_lint.py，修改 kb.py、README；`skills/` 下的改动是主会话做的
- [x] T2 lint SKILL.md 新建、save SKILL.md 修改，主会话（report）— lint SKILL.md 95 行，三条硬约束放在最前，片段一致性测试通过；save SKILL.md 第 6 步加了一段："没有新内容"时 log 必须写出 inbox 路径；save Spec 变更记录补了一行
- [x] T3 主会话复核与对抗抽查，并提交（report）
  - AC1：unittest 共 191 项全部通过；save 测试（`discover -p test_save.py`）全部通过
  - 抽查 1 重构等价：`git diff tests/test_save.py` 为空 ✓（直接 `python3 -m unittest tests.test_save` 会报找不到 vault_support，重构前也一样，属于运行方式问题，不是回归）
  - 抽查 2：断链有两个同名候选时，preview 的 diff 不含修复 ✓
  - 抽查 3：index 漏一页、多一条失效条目，preview 修 2 处，apply 后 HEAD 为 `lint: 安全修复 2 处`，包含 index.md 和 log.md，修后 check 0 ✓。第一次跑时临时库没有 git 身份，apply 提交失败（退出 1，按 Spec 保留已写入的文件、报告原因、不 reset），这是抽查脚本的环境问题；配好身份后通过
  - 抽查 4：不带 fix 的 lint 和 fix preview 前后 git 状态不变 ✓
  - 抽查 5：log 里写了路径的"没有新内容"inbox 不算积压，没写的那个算 ✓
  - 抽查 6：只被 index 链接的页面报孤儿；project 页不报 ✓；孤儿页归入"维护提示"组，severity=hint
  - AC2–AC4：test_lint 覆盖四类问题和分组顺序、三类安全修复、规模指标与"暂无数据"；指纹不匹配返回 3 见 test_lint 第 291 行
  - AC5、AC8：两份 SKILL.md 符合要求
- [ ] T4 真实环境验证 AC6、AC7（gate，模块最终验收）
