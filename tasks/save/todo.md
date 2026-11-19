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
- [ ] T4 真实沉淀第一条知识，AC5（gate）
- [ ] T5 Codex 跨宿主验证，AC6（gate，模块最终验收）
