---
captured: 2026-08-29
source: session
host: claude-code
project: proj-example
---
# 会话记录：从 agent 里调 codex exec 踩的两个坑（2026-08-29）

背景：Claude Code 主会话把任务派给 Codex 执行，直接在 Bash 里敲 `codex exec`。

坑 1：非 TTY 的 stdin 会让 `codex exec` 永久挂起。
- 症状：Bash 工具调用一直不返回，直到超时。
- 原因：codex exec 在 stdin 不是 TTY 时会等待从 stdin 读取输入。
- 解法：调用时加 `</dev/null`。delegate 插件的 wrapper 已经兜住。

坑 2：过程输出不重定向会整段涌进上下文。
- 实测 28–35KB 的过程输出，换来 170–250 字节的结论，百倍差距。
- 解法：过程日志写文件，只把结论和日志路径交回主会话；要证据时用 `sed -n` 取几行。

坑 3：`--write` 模式下只信 Codex 的自述会误判。
- 2026-08-29 实测：Codex 回复「我会改成 a+b，请确认」，读起来像做完了，但 `git status` 是空的。
- 解法：必须看 wrapper 打印的 Git 验收块（基线 HEAD + git status --short + git diff --stat），不看不算完。
