# Todo: ask

- [x] T0 修复模板日期，主会话（report）— init.py 页面模板保留 `YYYY-MM-DD`；test_vault_cli 补断言（模板不含具体日期、log 的 init 条目是真实日期）；真实知识库 5 个模板已修复并与新模板逐一比对一致，`kb check` 0 问题，知识库提交 `9d49c1a`；vault-contract Spec 已记变更
- [x] T1 检索脚本，派 Codex --write（report）— run `20261119152956.96628`，status=done，`--check` 通过；Git 验收块：基线 `eff82d3`，新增 ask.py、interface.json、interface.md、test_ask.py，修改 README、kb.py、check-manifests.py 和两个测试文件。比 Plan 多改了 `markdown.py`：给 Callout 加 `end_line`，并修正一个原有的边界问题（标注块后紧跟不带 `>` 的代码块时，原来会误判为仍在块内）；正文 body 不变，新增测试覆盖
- [x] T2 SKILL.md，主会话（report）— 90 行，四条硬约束放在最前（只读、结论只取 current、附出处、查不到明说并和模型自己的知识分开）；根目录解析片段由脚本注入，一致性测试通过
- [x] T3 主会话复核与对抗抽查，并提交（report）
  - AC1：unittest 共 162 项全部通过
  - AC2：契约字段由 test_ask 的 schema 断言覆盖；没有命中时退出 1，JSON 合法（抽查 6）
  - AC3：interface.json 契约 1.0、references/interface.md 已发布，check-manifests 校验 interface.json 并通过
  - AC4：SKILL.md 覆盖抽词、检索、读候选、按区域回答、出处、查不到明说、不写文件
  - 对抗抽查：1 只在 outdated 块命中的页面排在 current 页面之后 ✓；2 superseded 整页全部标 outdated 并带 superseded_by ✓；3 代码块命中按所在区域判为 current ✓；4 `a.b`、`(x)` 按字面量匹配 ✓；5 搜索前后 git 状态不变 ✓；6 没有命中时退出 1，pages 为空，ok=true ✓
- [x] T4 真实环境验证 AC5–AC7（gate，用户 2026-11-19 批准执行）
  - AC5：在 tab-leader 运行 `claude -p "/kb:ask Codex 里改了插件的 skill 为什么不生效？" --model haiku`。回答命中 `wiki/pitfalls/codex-plugin-cache-refresh.md`，每条依据都附绝对路径链接；直接回答为"Codex 读的是缓存副本，改了源码不会自动更新，要重新安装"；检索了 10 个词，命中 1 页；"知识库之外：无"
  - AC6：dispatch 样例复制到临时目录（git 提交信息用中文，否则会被用户的提交 hook 拦下），通过 `KB_CONFIG` 指向它，问"把机械活派给子代理省钱吗？"。直接回答是"不一定省钱。按现行判据……默认不派"；旧结论放在"历史与分歧"一节，写成"曾经认为……后被 2026-10-06 的整账实测推翻"；命中 2 页，临时知识库 git 状态不变。末尾的模块协调提醒来自 tab-leader 自己的规则，和 kb 无关
  - AC7：delegate 只读派单（tab-leader，effort low）。Codex 加载了缓存里的 `skills/ask/SKILL.md`，执行 `ask search Codex 插件 plugin skill 缓存 cache 生效 --json`，退出 0；读完页面后作答，每条附出处；知识库没有改动

## 最终验收

- [x] 用户 2026-11-19 批准最终验收（ask Spec 未修改；同时批准了 vault-contract Spec 在 T0 新增的那行变更记录）
