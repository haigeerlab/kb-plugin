# Todo: save

- [x] T1 save 脚本，派 Codex --write（report）— run `20261119133541.89560`，status=done，`--check` 通过；Git 验收块：基线 `38462d4`，修改 README.md 和 kb.py，新增 save.py 和 test_save.py；`skills/save/` 是主会话写的，确认 Codex 没有改动
- [x] T2 SKILL.md，主会话（report）— 10 个编号步骤，三条硬约束放在最前；根目录解析片段由脚本从 reference 注入，一致性测试通过；修正了一处会让模型踩坑的写法：示例 frontmatter 里不能写行内注释（解析器会把注释当成值）
- [x] T3 主会话复核与对抗抽查，并提交（report）
  - AC1：unittest 共 142 项全部通过（新增 36 项）
  - AC2：对抗抽查（临时知识库，每项单独构造）：
    1. 草稿改已有 inbox → 退出 1，`[path] inbox/ 只允许新建文件`
    2. 两个 inbox → 退出 1，`[path] 一次 save 必须恰好包含 1 个 inbox/ 下的新文件`
    3. preview 后知识库新增一个提交 → apply 退出 3，HEAD 不变
    4. 草稿含运行时拼接的假密钥 → 退出 1，`redaction`，输出里没有完整假密钥
    5. 新页面没进 index → 退出 1，`index`
    6. 写入中途失败回滚 → test_save.py 第 321、346、368 行覆盖（写入失败完整回滚、准备阶段失败不写、commit 失败保留文件并打码报告）
  - AC3：test_save 的端到端用例连续 save 三次（新建坑页 → 新建决策页 → 冲突处置生成 `[!outdated]`），每次 0 问题，3 个 save 提交，inbox 没有被改动
  - AC4：SKILL.md 覆盖范围确认、inbox 提炼规则、检索两步、四种处置、模板、index 和 log 格式、preview → 原样展示 → 明确确认 → apply → 报告；敏感内容引用 SCHEMA
  - AC7：README 把 `/kb:save` 标为已实现，写了流程和退出码
  - 通读 save.py：叠加校验用 `git clone --no-hardlinks` 保留历史，再同步工作区；原子写入用临时文件加 os.replace，失败时逆序恢复备份、删除新建文件和目录
- [x] T4 真实沉淀第一条知识，AC5（gate，用户 2026-11-19 批准执行；写入前用户确认了预览）
  - 通过已安装的 `kb:save` skill 执行（Claude Code 把 `${CLAUDE_PLUGIN_ROOT}` 代入成了实际路径）
  - 检索：index 为空；`rg` 搜 缓存、cache、插件、plugin、codex、marketplace、市场，wiki 没有命中 → 新建 pitfall
  - preview 一次通过，指纹 `4a38d5ed9fb66cdd`；用户确认后 apply，知识库提交 `d591ba1`（save: Codex 插件改了 skill 不生效：读的是缓存副本），`kb check` 0 问题，工作区干净；草稿目录已删除
  - 发现待修项：知识库 `templates/*.md` 的日期在 init 时被替换成了 2026-11-19，没有保留占位符；以后照抄会写错日期
- [x] T5 Codex 跨宿主验证，AC6（gate，用户 2026-11-19 批准执行）
  - delegate 只读派单（在 tab-leader 目录）：Codex 加载缓存里的 `skills/save/SKILL.md`，doctor 退出 0，读了 SCHEMA 和 index
  - 第 4 步检索 15 个词（Codex、缓存、cache、插件、plugin、skill、技能、副本、刷新、refresh、marketplace、upgrade、Git，以及两条命令原文），index 和全文都命中 `wiki/pitfalls/codex-plugin-cache-refresh.md`，完整读过
  - 第 5 步处置：**没有新内容**，理由是现有页面已覆盖全部事实，没有新增内容也没有冲突 → 跨宿主去重成立
  - 只读沙箱（`sandbox_mode` is `read-only`）不允许 mktemp 写草稿，preview 没有运行，按 Plan 预设的退路验收到第 5 步；Codex 可写模式下的 preview 留到 MVP 验收实测
  - 知识库 HEAD 没变，工作区干净

## 最终验收

- [x] 用户 2026-11-19 批准最终验收（Spec 未修改）
- [ ] 延期：AC14 互链规则的真实环境确认（下一次真实 save 或 compile 的预览里出现 `## 相关` 或"未发现相关页面"）；恢复条件：用户下一次在真实工作中触发 save 或 compile
