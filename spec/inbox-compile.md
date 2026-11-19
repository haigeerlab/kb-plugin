<!-- spec-guard: review approved f3054e5a018b -->

# Spec: inbox-compile

## Objective

能力图第 7 个模块，Phase 5 的第一个。`/kb:compile` 用于**批量**处理两类还没进 wiki 的东西：

1. **inbox 积压**：已经在 inbox 里、但没有被任何页面引用的条目。lint 的"inbox 积压"提示列出的就是这些。以后 delegate-lessons 会往 inbox 里写 Codex 执行中得到的教训，它们也属于这一类。
2. **候选会话**：有可能包含可沉淀经验的历史会话。session-capture 模块（下一个模块）会在每次会话结束时，静默地往队列里记一条指针；compile 负责回读这些会话，从中提炼经验。

目标是 PRD 场景 S4 和"每周整理约 5 分钟"：你先看一张候选清单，挑出要处理的；再看一次所有预览，确认一次；之后逐条写入。

**本模块定义候选队列的格式**，session-capture 只负责往队列里写。

用户：你本人，每周或积压较多时跑一次。

## 要你确认的假设

1. **候选队列放在本机状态目录，不进知识库**：`~/.local/state/kb/candidates.jsonl`。环境变量 `KB_STATE_DIR` 可以改位置，测试用。每行一条：`{"id", "session_id", "transcript_path", "cwd", "reason", "ended_at", "status"}`，`status` 取 `pending`、`compiled`、`dropped`、`expired` 之一。理由：指针里是本机路径和会话 ID，不是知识，不该进 git，也不该同步到 GitHub。
2. **会话记录要经过脚本提取才给模型看**：`kb.py candidates show <id>` 只输出 user 和 assistant 的文本，跳过工具输出、附件和 hook 注入的内容，**先打码敏感内容**（复用 redaction 的规则），再截断到字数上限（默认 40000 字，可调）。一个会话文件动辄几 MB，直接读既费上下文，也会把工具输出里的密钥带进来。
3. **会话记录有保留期**：Claude Code 默认只保留 30 天，到期**静默删除**（已查官方文档 `cleanupPeriodDays`）。处理方式：
   - 会话文件已经不在了 → 标为 `expired`；
   - 超过 25 天还没处理的候选，清单里标"即将过期"。
4. **处理流程分三步，你只做两次决定**：
   - **第一步，清单**：脚本列出全部待处理项（inbox 积压 + `pending` 候选）。模型给每项写一句话摘要，并给出建议：编译 / 丢弃 / 先留着。**你挑出要编译的。**
   - **第二步，批量预览**：模型对每个选中项按 save 的规则写草稿，各自跑一次 preview，然后把所有预览（处置、文件清单、完整 diff、指纹）放在一条回复里给你。**你确认全部或其中一部分。**
   - **第三步，逐条写入**：每一项都是独立的事务，有自己的指纹和自己的提交（`compile: <标题>`），按顺序 apply；遇到失败就停下来报告，已经写入的不回退。
   
   被你标为"丢弃"的候选只改队列状态，知识库什么都不写。
5. **两类来源的写法不同**：
   - **inbox 积压**：不新建 inbox 文件，页面的 `raw` 引用已有的那条 inbox；
   - **候选会话**：和 save 一样，新建一条 inbox 摘录，承重事实从会话里逐字摘出来。
   
   因此写入器要增加 `compile` 操作：允许新建 0 个或 1 个 inbox 文件，其余白名单和 save 相同。log 里用 `compile` 操作名（vault-contract 已经预留了这个名字）。
6. **一个候选会话里可能有好几条经验**：在第一步清单里拆成多项列出，每项单独处理。处理完一个会话的全部项之后，候选标为 `compiled`。
7. **候选入队的命令也由本模块提供**：`kb.py candidates add --session-id … --transcript … --cwd … --reason …`。session-capture 的 hook 将来调用它；现在可以手动调用，用来验收。同一个 `session_id` 重复入队时，只更新已有那条，不会新增重复记录。
8. **本模块只支持 Claude Code 的会话记录**。Codex 的会话格式不同，session-capture 也只做 Claude 侧，Codex 侧留到以后。
9. **compile 不负责"把 ask 的回答归档成页面"**。PRD 把归档放在 Phase 5，但能力图里没有对应的模块；需要时用 `add-module` 单独插入。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py candidates add --session-id <id> --transcript <路径> --cwd <路径> --reason <原因>
python3 -B plugins/kb/scripts/kb.py candidates list [--json]              # inbox 积压 + pending 候选；标出即将过期和已过期的
python3 -B plugins/kb/scripts/kb.py candidates show <id> [--max-chars N]   # 提取并打码后的对话文本
python3 -B plugins/kb/scripts/kb.py candidates mark <id> --status compiled|dropped
python3 -B plugins/kb/scripts/kb.py compile preview <草稿目录> [--json]     # 同 save preview，操作为 compile
python3 -B plugins/kb/scripts/kb.py compile apply <草稿目录> --confirm <指纹> [--json]
```

`compile preview` 和 `compile apply` 的退出码沿用 save 的约定（0、1、2、3），提交失败时同样生成待提交记录，由 `commit-pending` 收尾。

## Project Structure（本模块新增或修改）

```
plugins/kb/
├── skills/compile/SKILL.md          # 新增（主会话写）
├── scripts/kblib/candidates.py      # 新增：队列读写、清单、会话记录提取与打码
├── scripts/kblib/compile.py         # 新增：compile 操作的草稿校验（0 或 1 个 inbox），调用 writer.publish
├── scripts/kblib/writer.py          # 修改：支持 operation=compile
└── scripts/kb.py                    # 修改：candidates、compile 子命令
tests/test_candidates.py
tests/test_compile.py
tests/fixtures/transcripts/          # 构造的会话记录样例（含工具输出、附件、假密钥）
README.md
```

## Testing Strategy

- **队列**：入队、按 `session_id` 去重、状态流转；`KB_STATE_DIR` 隔离；JSON 行损坏时报告行号，不崩溃。
- **提取**：只保留 user 和 assistant 的文本；工具输出、附件、hook 注入的内容都被跳过；运行时拼接的假密钥在输出里被打码；截断生效并标出"已截断"。
- **过期**：会话文件不存在时 → `expired`；超过 25 天 → 标"即将过期"（边界值测试）。
- **清单**：inbox 积压的判定和 lint 一致（复用同一份逻辑，log 里写了路径的"没有新内容"条目要排除）。
- **compile 草稿**：
  - 积压项 0 个新 inbox → 通过；候选项 1 个新 inbox → 通过；2 个 → 拒绝；
  - 改动已有的 inbox → 拒绝；
  - 提交信息为 `compile: <标题>`；log 条目的操作名为 `compile`。
- **重构保护**：save、lint、commit-pending 原有测试保持全绿。
- **端到端**：临时知识库里放一条积压 inbox 和一条候选会话样例，跑完清单 → 预览 → 两次 apply，得到两个 compile 提交，`kb check` 0 问题，候选标为 `compiled`，lint 不再报积压。

## Boundaries

- **总是**：会话记录先打码再给模型；每项写入前都要你确认；每项独立提交。
- **先问**：第一步挑选、第二步确认；修改 `~/.local/state/kb/` 以外的任何本机配置。
- **不做**：注册 SessionEnd hook（那是 session-capture 的事）；读 Codex 会话；把会话全文存进知识库；自动丢弃候选（丢弃也要你决定）；归档 ask 的回答。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖 Testing Strategy 的每一项；save、lint、commit-pending 的原有测试保持全绿。
- **AC2** `candidates show` 对样例会话只输出对话文本，假密钥被打码，超长时截断并有标注。
- **AC3** 清单同时列出 inbox 积压和 `pending` 候选，标出即将过期和已过期的项；已过期的候选自动转为 `expired`。
- **AC4** compile 的写入复用 writer：0 个或 1 个新 inbox 的规则、指纹、原子写入、待提交记录都生效。
- **AC5** SKILL.md 写清三步流程，以及两类来源各自的写法；第一步和第二步必须等你明确回复，一项失败就停下来。
- **AC6（真实环境）** 从你最近的真实会话里挑 1 个（我先列出最近几个会话的项目名和时间，由你来挑），用 `candidates add` 手动入队，然后在本会话里走一遍 `/kb:compile`：你在清单里决定编译或丢弃；如果选了编译，就看预览、确认、写入，`kb check` 0 问题。
- **AC7（跨宿主）** 通过 delegate 只读派 Codex 跑 `/kb:compile` 的第一步（清单），确认 Codex 也能读队列、提取会话记录。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/skills/compile/SKILL.md` | 新建 |
| `README.md` | 修改：`/kb:compile` 标为已实现，写明候选队列的位置和格式、三步流程 |

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
