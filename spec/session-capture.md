<!-- spec-guard: review approved a51f28707a98 -->

# Spec: session-capture

## Objective

能力图第 8 个模块。在每次 Claude Code 会话结束时，通过 SessionEnd hook **静默**地往候选队列记一条指针（`candidates add`）。不打扰你，不读会话内容，也不写知识库。下次 `/kb:compile` 时，这些会话会出现在清单里，由你决定编译还是丢弃。这就是 PRD 第 4 题定下的"静默记指针"。

这是 kb 的**第一个自动行为**。插件装好后，它会在你**所有**项目的会话结束时触发，所以本 Spec 的重点是：不出错、不拖慢退出、不越界、能关掉。

用户：你本人，被动受益。

## 已核实的事实

- SessionEnd hook 拿到的输入包括 `session_id`、`transcript_path`、`cwd`、`reason`；`reason` 的取值有 `clear`、`resume`、`logout`、`prompt_input_exit`、`other`。SessionEnd **不能阻止会话结束**，它的 JSON 输出会被丢弃（官方 hooks 文档）。
- 本机最近 60 个会话的 `entrypoint` 都是 `claude-desktop`，即你基本都在桌面 app 里使用。今天用 `claude -p` 跑的验收会话，在过去 24 小时的会话记录里一个都没有出现；旧的 `sdk-cli` 入口只出现在 module-crew 自动开的子会话里。所以**不能靠 `entrypoint` 过滤**。
- 插件 hook 写在插件目录的 `hooks/hooks.json`，命令里用 `CLAUDE_PLUGIN_ROOT` 定位脚本（本机 spec-guard 的先例）。

## 要你确认的假设

1. **只做 Claude Code 侧**。Codex 的会话格式不同，compile 也只支持 Claude 的会话记录。Codex 侧留到以后。
2. **按内容过滤，不按入口过滤**：会话里你亲手输入的消息（判定口径和 `candidates show` 一样：非注入、非工具结果、非子代理）**少于 2 条**就不入队。这样能挡掉一次性的 `claude -p`、只问了一句就关掉的会话，以及大多数自动化子会话。阈值可以配置。
3. **默认开启，可以关掉**：`~/.config/kb/config.json` 增加可选字段：
   - `"session_capture": false` 表示整体关闭；
   - `"capture_min_user_messages": 2` 是阈值；
   - `"capture_ignore_dirs": [...]` 是要排除的目录前缀，例如你不想记录的公司项目目录，或者 module-crew 自动开的 `*-crew` 目录。默认为空。
   
   新增 `kb.py capture status` 命令，显示当前是否开启、阈值和排除目录，以及队列里待处理的数量。改配置走现有的 `config` 命令风格：先预览，`--confirm` 才写入。
4. **hook 绝不失败、绝不拖慢退出**：
   - 脚本只用 Python 标准库；
   - 读会话记录时只数用户消息，读到第 2 条就停，不读完整个文件；
   - 设置超时 5 秒；
   - **任何异常都以 0 退出**，原因写进状态目录里的 `capture.log`，只追加，超过 1MB 时截掉前半；
   - 不往 stdout 和 stderr 打任何东西。
5. **只写候选队列**：hook 唯一的写入是 `~/.local/state/kb/candidates.jsonl`（经由 `candidates add`，同一会话去重）和 `capture.log`。不碰知识库、不碰配置、不联网。这一点要按 MVP 验收 V6 的方法重新核对一遍。
6. **知识库目录和插件目录本身的会话也照样记录**。在这两个目录里开发 kb 的经验同样值得沉淀。如果不想要，可以把它们加进排除目录。
7. **SessionEnd 在桌面 app 里会不会触发，需要实测**。你的会话几乎都在桌面 app 里，如果它在桌面 app 里不触发，这个模块对你就基本没用。AC6 专门验证这一点；如果不触发，就停下来和你商量替代方案（例如改用 Stop hook，在第 N 轮时记一次）。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py capture status [--json]
python3 -B plugins/kb/scripts/kb.py capture hook < sessionend-input.json   # hook 调用的入口，从 stdin 读 JSON
python3 -B plugins/kb/scripts/kb.py config set-capture --enabled true|false [--min-user-messages N] [--ignore-dir 路径 ...] [--confirm]
```

## Project Structure（本模块新增或修改）

```
plugins/kb/
├── hooks/hooks.json                 # 新增：SessionEnd → capture hook（只注册在 Claude 清单里）
├── .claude-plugin/plugin.json       # 修改（如需要）：声明 hooks
├── scripts/kblib/capture.py         # 新增：读 stdin、过滤、入队、写日志、永远退出 0
├── scripts/kblib/config.py          # 修改：读取三个可选字段；set-capture
└── scripts/kb.py                    # 修改：capture status|hook、config set-capture
tests/test_capture.py
scripts/check-manifests.py           # 修改：校验 hooks.json 能解析、引用的脚本存在
README.md
```

## Testing Strategy

- 过滤：用户消息 0、1、2 条的会话；注入消息、工具结果、子代理消息不计数；阈值可配置；排除目录按前缀匹配。
- 健壮性：stdin 为空、JSON 损坏、缺字段、`transcript_path` 不存在、状态目录不可写、配置损坏，**全部以 0 退出**，stdout 和 stderr 为空，原因写进 `capture.log`。
- 性能：一个 5MB 的会话记录、第 2 条用户消息在前部时，执行时间在 1 秒以内（测试断言读取在第 2 条后停止）。
- 关闭：`session_capture: false` 时不入队。
- 去重：同一 `session_id` 触发两次，队列里只有一条。
- 只写指定位置：测试前后，知识库和配置目录没有任何变化。
- 清单：`check-manifests.py` 校验 hooks.json。

## Boundaries

- **总是**：任何情况下 hook 都以 0 退出、不输出；只写候选队列和日志。
- **先问**：改你真实的 `~/.config/kb/config.json`（排除目录等）。
- **不做**：读会话内容（只数用户消息）、调用模型、写知识库、提示你、Codex 侧采集、Stop hook（除非 AC6 证明 SessionEnd 在桌面 app 不触发，并且你同意改方案）。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖上面 Testing Strategy 的每一项。
- **AC2** 所有异常输入下 hook 都以 0 退出，stdout 和 stderr 为空，原因进日志。
- **AC3** 5MB 会话记录的处理时间在 1 秒以内。
- **AC4** `capture status` 能如实显示开关、阈值、排除目录、待处理数量；`config set-capture` 先预览后写入。
- **AC5** 按 V6 的方法核对：新增的写入点只有候选队列和 `capture.log`。
- **AC6（真实环境，关键）** 刷新插件后，你**在桌面 app 里**新开一个会话，随便聊 2 句以上然后关掉；我检查队列里是否出现了这个会话。如果没有出现，停下来，和你商量替代方案。
- **AC7** README 和 `capture status` 的输出都写清：会记录什么（只有路径和会话 ID）、不记录什么、怎么关闭。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `README.md` | 新增"会话结束自动记候选"一节：记录内容、过滤规则、开关 |

## Open Questions

无。（假设 7 由 AC6 实测决定。）

## 变更记录

- 2026-11-19 初稿。
