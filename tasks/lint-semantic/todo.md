# Todo: lint-semantic

- [x] T0 样例知识库（四类埋点加干扰项），主会话（report）— `5f64b85`：8 页，临时 git 副本上 `kb check` 0 问题；README 列出埋点、干扰项与期望
- [x] T1 实现，派 Codex --write（report）— run `20261120010032.5508`，status=done，`--check` 在本机通过（308 项）；Git 验收块：基线 `5f64b85`，新增 semantic.py、test_semantic.py（22 项），修改 kb.py、README；未碰 skills、fixture、原有测试；未提交。自定截断细节：每页正文 4000 字符、截断路径清单限额
- [x] T2 lint SKILL 与 lint 变更记录，主会话（report）— `86d5815`：第 6 节语义体检；`spec/lint.md` 加一行变更记录（批准后修订，待用户复审）
- [x] T3 主会话复核与 6 项对抗抽查，并提交（report）
  - 通读 semantic.py：现行正文复用 markdown 标注块边界；引文核对复用 evidence 的规范化与包含判断；路径拒绝 `..`、绝对路径和非 wiki/；截断先截最新页
  - 抽查 1：fluxctl 矛盾对在候选里，retry（disputed 互指）不在；0.9.3 在过期线索里，1.4.2（outdated 块内）不在；relayd 在缺页线索里，pkgsync 不在；never-force-push-shared 命中三种升级信号，friday-release 只有祈使句；现行正文不含标注块文字
  - 抽查 2：pack 前后样例文件哈希与 git status 不变
  - 抽查 3：真引文保留；改一个字、引自 outdated 块、`wiki/../` 路径均被剔除（退出码 1）
  - 抽查 4：加 120 页大页面后输出正好 60000 字节，truncated=true，矛盾候选 30 对
  - 抽查 5：运行时拼接的假密钥在 JSON 与文本报告中都无明文
  - 抽查 6：原有测试零改动；本机不设 KB_DELEGATE_DIR 跑全量 308 项通过
  - 主会话小改：文本报告的"已剔除"条目加上类别与页面（原先只打印错误原因），语义测试与全量测试通过
- [ ] T4 样例与真实知识库的语义体检（gate，模块最终验收）
