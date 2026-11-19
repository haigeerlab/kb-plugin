<!-- spec-guard: review approved dac33085e558 -->

# Spec: delegate-lessons

## Objective

能力图第 9 个模块。让 Codex 通过 delegate 执行任务时踩到的坑、得出的结论**自动回流**到 kb，成为 `/kb:compile` 清单里的候选；由你决定编译或丢弃。这对应 PRD 场景 S5"Codex 经验回流"。

**不改 delegate**（Phase 0 和 PRD 6.5 已经定了）：kb 只读取 delegate 已经公开的产物，也就是结果文件和答复文件。

用户：你本人，被动受益。你在 `/kb:compile` 时会多看到一类候选："来自 Codex 的执行结果"。

## 已核实的事实

- delegate 0.8.6，接口 1.3。每次 run 都会写 `${TMPDIR}/delegate/<runId>.result.json`（schema 1），字段包括 `kind`（run 或 review）、`status`（done、needs-input、timeout、unmarked、failed、interrupted、unreaped、empty）、`repository`、`write`、`chainRoot`、`parent`、`commands`（命令和退出码）、`changedFiles`、`startedAt`、`endedAt`，以及 `answer.path`（Codex 最终答复正文的文件）。契约见 delegate 仓库 `spec/run-result.md` 和 `interface.json` 的 `run.result`。
- 这些文件放在**系统临时目录**，delegate 只保留最近 50 组（本机目录现有 122 个文件）。macOS 也会清理长期不用的临时文件。**不及时取快照就会丢失。**
- PRD 原来设想"在 delegate 验收块里加 `lessons` 字段"，这需要改 delegate，按生态规则要走总负责人。本 Spec 改为由 kb 自己从答复里提取，不需要改 delegate。

## 要你确认的假设

1. **什么时候收集：搭 session-capture 的 SessionEnd hook 顺带做，再加一个手动命令。**
   - 每次 Claude Code 会话结束时，hook 在记候选会话的同时，扫一遍 delegate 结果目录，给**新出现的、已结束的** run 取快照。delegate 几乎都是在 Claude Code 会话里调用的，会话结束时扫描最及时，也不用新增 hook。
   - `kb.py candidates scan-delegate` 可以手动执行；`/kb:compile` 第一步也会先跑一次，作为兜底。
   - 扫描受到 hook 的 5 秒时限约束，只做轻量的复制和过滤；单次最多处理 20 个新结果，没处理完的留给下一次。
2. **收集哪些结果：**
   - `kind` 为 `run`（review 是代码审查结论，不是经验，不收）；
   - 状态是"已结束"的：`done`、`failed`、`timeout`、`unmarked`、`unreaped`、`empty`。`needs-input` 表示链条还没结束，先跳过，等同一条链有了结束状态再收；
   - **同一条可续跑链只收一次**，按 `chainRoot` 去重，收链条里最后一个结束的 run；
   - 答复少于 200 字节、且所有命令都成功的 run 不收：这类多半是"改好了"之类的简短回复，没有经验可言。阈值可以配置。
3. **快照内容（存本机，不进知识库）**：`~/.local/state/kb/delegate/<runId>.json`，包括状态、仓库路径、读写模式、开始和结束时间、改动文件列表、**失败的命令**（命令行截断到 300 字，附退出码），以及**答复正文**（截断到 20000 字）。原始结果文件不复制，只提取这些字段。快照入队时作为一类新的候选：`source: delegate`。
4. **和 compile 衔接（会改到 inbox-compile 已验收的行为）**：
   - `candidates list` 同时列出 delegate 候选，显示仓库名、状态、时间；
   - `candidates show <id>` 对 delegate 候选输出快照内容（同样先打码）；
   - compile SKILL 的第 2 步写明：delegate 候选重点看答复里的"发现、原因、解法"和失败的命令；**全是"完成了"之类没有可复用经验的，建议丢弃**；
   - 编译时新建的 inbox 条目 `source` 写 `delegate`（vault-contract 已经允许这个值），`host` 写 `codex`。
   
   这部分会在 inbox-compile 的 Spec 里加一行变更记录，验收时一并给你看。
5. **不做 delegate 提示词侧的改动**：比如让 Codex 在答复末尾固定输出"经验"一节。这需要每次派单都带 `--rules-file`，或者改 delegate，都超出本模块范围。以后如果发现答复里经验太稀疏，可以再单独提。
6. **只读 delegate 的产物**：不修改、不删除 delegate 目录里的任何文件。
7. **开关**：沿用 session-capture 的配置风格，新增 `delegate_capture`（默认开启）和 `delegate_min_answer_bytes`（默认 200）。`capture status` 显示这两项，以及最近一次扫描的时间和处理了多少个结果。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py candidates scan-delegate [--json]
python3 -B plugins/kb/scripts/kb.py candidates list [--json]          # 同时列出 delegate 候选
python3 -B plugins/kb/scripts/kb.py candidates show <id>              # delegate 候选输出快照
python3 -B plugins/kb/scripts/kb.py capture status                    # 显示 delegate 采集的开关与最近扫描
```

环境变量 `KB_DELEGATE_DIR` 可以指定 delegate 结果目录，测试时用；默认是 `${TMPDIR:-/tmp}/delegate`。

## Project Structure（本模块新增或修改）

```
plugins/kb/scripts/kblib/delegate_lessons.py   # 新增：扫描、过滤、按链去重、取快照、入队
plugins/kb/scripts/kblib/candidates.py         # 修改：候选增加 source 字段（session、delegate）；list 和 show 支持 delegate
plugins/kb/scripts/kblib/capture.py            # 修改：SessionEnd hook 顺带调用扫描（受时限和数量上限约束，任何异常都吞掉）
plugins/kb/scripts/kblib/config.py             # 修改：两个新配置字段
plugins/kb/scripts/kb.py                       # 修改：candidates scan-delegate
plugins/kb/skills/compile/SKILL.md             # 修改（主会话）：第 2 步对 delegate 候选的读法和建议
tests/test_delegate_lessons.py
tests/fixtures/delegate/                       # 构造的结果文件和答复文件（结构参照真实文件，内容虚构）
README.md
```

## Testing Strategy

- 过滤：`kind=review` 不收；`needs-input` 跳过，同一条链之后出现 `done` 再收；按 `chainRoot` 去重；答复短且命令全成功时不收，答复短但有失败命令时收；阈值可以配置。
- 快照：字段完整；失败命令和答复按长度截断；原始文件不被修改；只在状态目录下写入。
- 增量：已经取过快照的 run 不重复处理；单次最多 20 个，剩下的下次再处理。
- 健壮性：目录不存在、结果文件损坏、答复文件缺失、`schema` 不是 1，都跳过并记日志，不崩溃；在 hook 里调用时依然以 0 退出、不输出。
- 衔接：`candidates list` 和 `show` 支持 delegate 候选，show 输出经过打码（假密钥在运行时拼接）；compile 用 `source: delegate` 新建 inbox 后 `kb check` 为 0 问题。
- 回归：session-capture、candidates、compile 原有测试保持全绿。
- 性能：结果目录里有 200 个文件、其中 20 个是新的时，hook 总耗时小于 1 秒。

## Boundaries

- **总是**：只读 delegate 目录；快照存本机；hook 永远以 0 退出、不输出。
- **先问**：改你真实的配置；编译 delegate 候选（照常走 compile 的两次确认）。
- **不做**：修改 delegate；读 Codex 自己的会话文件；收集 review 结果；自动写知识库。

## Success Criteria

- **AC1** 单元测试全部通过；session-capture、candidates、compile 原有测试保持全绿。
- **AC2** 过滤规则正确（review、needs-input、按链去重、短答复），增量处理不重复。
- **AC3** hook 加上扫描后，所有异常输入下依然以 0 退出、不输出；200 个文件的目录处理时间小于 1 秒。
- **AC4** 只读 delegate 目录（测试前后文件的哈希不变），只往状态目录写快照。
- **AC5** compile SKILL 写明 delegate 候选的读法和"没有经验就建议丢弃"。
- **AC6（真实环境）** 对本机现有的真实 delegate 结果跑一次 `scan-delegate`（今天这个会话里有十几次真实派单）：列出被收集和被跳过的数量和理由，你在 `/kb:compile` 清单里看到 delegate 候选，从中挑一条编译或者全部丢弃。挑出的内容由你决定，脱敏规则照常生效。
- **AC7** README 写清 delegate 回流的机制、收集范围、开关。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `README.md` | 新增"Codex 执行经验回流"一节 |
| `plugins/kb/skills/compile/SKILL.md` | 修改第 2 步 |
| `spec/inbox-compile.md` | 增加一行变更记录（新增 delegate 来源） |

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
