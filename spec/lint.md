<!-- spec-guard: review approved 6ae55297000e -->

# Spec: lint

## Objective

能力图第 6 个模块，也是 MVP 的最后一个。`/kb:lint` 给知识库做一次**确定性**体检，输出一份报告，内容包括：

- `kb check` 的全部问题，按影响分组；
- lint 独有的几项检查：孤儿页、疑似过期、inbox 积压；
- 规模指标。

对少数"只有一个正确改法"的问题，提供**安全修复**：先给预览，你确认后再写入并提交。语义层面的检查（矛盾、重复、建议升级成规则）属于 Phase 5 的 lint-semantic，不在本模块范围内。

用户：你本人。可以定期跑，也可以在大量 save 之后跑一次。

## 要你确认的假设

1. **报告只输出、不落盘。** 报告打印到终端，或者用 `--json` 输出，不写进知识库。只有确认执行安全修复时才写知识库，并在 log 里追加一条 `## [日期] lint | …`。
2. **lint 在 `kb check` 之外多查四项，全部是提示级别，不会让 `kb check` 失败：**
   - **孤儿页**：没有任何**其他 wiki 页面**链接过来的页面（index 里的链接不算）。project 枢纽页不算孤儿。
   - **疑似过期**：`updated` 距今超过 180 天的 `current` 页面，提示复查。天数可以用 `--stale-days` 调。
   - **inbox 积压**：没有被任何页面的 `raw` 引用过的 inbox 条目。这类条目要么是"没有新内容"的 save，要么就是还没编译的积压。为了区分这两种情况，**save 判为"没有新内容"时，log 条目正文里必须写出 inbox 路径**，lint 据此把它们排除在积压之外。这需要对 save 的 SKILL.md 做一处小修改，记在 save 的 Spec 变更记录里。
   - **规模指标**：wiki 页数、index.md 字节数，对照 PRD 定的阈值（300 页、40KB）。PRD 的第三个指标"ask 平均读文件数"目前没有数据来源（ask 不记日志），报告里如实写"暂无数据"，不编造。
3. **安全修复只做三类"唯一正确改法"的事：**
   - wiki 页没进 index：在对应类型一节补一行，标题取 frontmatter 的 title，摘要写"（待补摘要）"，日期取 updated；
   - index 指向不存在的页面：删除这一行；
   - 页面里的链接断了，但知识库里**恰好只有一个**同名文件：把链接改成指向它。
   
   其余问题一律只报告，不自动修。
4. **安全修复复用 save 的写入路径**：同样叠加副本做全量校验、同样的预览指纹、同样的原子写入和本地提交（提交信息为 `lint: 安全修复 N 处`）。实现上，把 save.py 里通用的部分抽成一个共享模块，save 和 lint 都调用它；抽完之后，save 原有的 36 项测试必须全部照常通过。lint 修复不涉及 inbox，所以不受 save"恰好 1 个 inbox"这条规则约束。
5. **分组按影响排列**：导航断裂（断链、index）→ 内容可信度（evidence、raw-ref、callout、immutable、redaction）→ 格式（frontmatter、sections、filename、inbox、log、schema-version）→ 维护提示（孤儿页、疑似过期、inbox 积压）。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py lint [--json] [--stale-days N]          # 体检报告
python3 -B plugins/kb/scripts/kb.py lint fix preview [--json]               # 安全修复预览
python3 -B plugins/kb/scripts/kb.py lint fix apply --confirm <指纹> [--json]  # 确认写入并提交
```

退出码：
- `lint`：0 表示没有 check 级问题（可能有提示级），1 表示有 check 级问题，2 表示配置或用法错误。
- `lint fix`：沿用 save 的约定，0 成功，1 校验失败，2 用法错误，3 指纹不匹配。没有可修复的问题时 preview 退出 0，并说明"无需修复"。

## Project Structure（本模块新增或修改）

```
plugins/kb/
├── skills/lint/SKILL.md            # 新增（主会话写）
├── skills/save/SKILL.md            # 修改（主会话）："没有新内容"时 log 正文写 inbox 路径
├── scripts/kblib/lint.py           # 新增：额外检查、分组、规模指标、安全修复的草稿生成
├── scripts/kblib/writer.py         # 新增：从 save.py 抽出的共享写入路径（叠加校验、指纹、diff、原子写入、提交）
├── scripts/kblib/save.py           # 修改：改为调用 writer.py，行为不变
└── scripts/kb.py                   # 修改：lint 子命令
tests/test_lint.py
README.md
```

## Testing Strategy

- 每项额外检查都有命中用例和不命中用例：孤儿页（index 链接不算、project 页除外）、疑似过期（边界值 180 天，`--stale-days`）、inbox 积压（log 里写了路径的"没有新内容"条目被排除）。
- 分组顺序、规模指标的数值、"暂无数据"字样。
- 安全修复三类各一个用例；不属于这三类的问题（比如断链有两个同名候选）不修；修复后 `kb check` 为 0 问题。
- 指纹不匹配时返回 3；修复和 log 条目在同一个提交里。
- 重构保护：save 原有测试全部通过；writer.py 的行为由 save 和 lint 两边的测试共同覆盖。
- 只读：`lint`（不带 fix）前后，知识库的文件和 git 状态都不变。

## Boundaries

- **总是**：报告不落盘；修复前先预览；修复走共享写入路径。
- **先问**：每次 `lint fix apply`。
- **不做**：语义检查（矛盾、重复、建议升级成规则，属于 lint-semantic）；修复上面三类以外的问题；删除页面；改 inbox 和 raw；调用模型。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖 Testing Strategy 的每一项；save 原有测试保持全绿。
- **AC2** 在一个人为制造了问题的知识库上，`lint` 报出至少四类问题（断链、孤儿页、index 不一致、出处不符），分组顺序正确。这一条对应 MVP 验收第 5 条。
- **AC3** `lint fix` 只修三类安全问题，修后 `kb check` 为 0 问题，提交里同时包含修复和 log 条目；指纹不匹配时返回 3。
- **AC4** 规模指标正确；"ask 平均读文件数"一项显示"暂无数据"。
- **AC5** SKILL.md 写清：运行 lint → 按分组解释（区分事实和建议）→ 有可安全修复的问题就给预览 → 你明确确认后 apply → 报告提交号；不属于安全修复的问题给出处理建议，但不动手。
- **AC6（真实环境）** 在你真实的知识库上跑 `/kb:lint`：check 级 0 问题；孤儿页提示会列出那一页（它目前没有其他页面链接过来），并作为提示级正确呈现。
- **AC7（跨宿主）** 通过 delegate **只读**派 Codex 跑 `/kb:lint` 的报告部分（不 fix），输出和 Claude Code 一致。
- **AC8** save 的 SKILL.md 已修改，"没有新内容"时 log 里写出 inbox 路径；save 的 Spec 变更记录也补了一行。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/skills/lint/SKILL.md` | 新建 |
| `plugins/kb/skills/save/SKILL.md` | 修改一处 |
| `README.md` | 修改：`/kb:lint` 标为已实现，补命令和退出码 |

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
- 2026-11-20（lint-semantic 引入）：`/kb:lint` 增加可选的语义段（用户明确要求时才跑，只出报告），新增 `lint semantic-pack`、`lint semantic-verify` 两个子命令；确定性部分和安全修复的行为不变。详见 [lint-semantic](lint-semantic.md)。
