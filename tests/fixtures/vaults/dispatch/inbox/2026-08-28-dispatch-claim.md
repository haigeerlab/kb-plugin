---
captured: 2026-08-28
source: session
host: claude-code
project: proj-example
---
# 决策记录：机械活派给子代理（2026-08-28）

依据：近 14 天全部 transcript 统计，isSidechain=true 为 0 行，19 个 subagent 一次没跑过；同期主会话 Opus 输出 40.26M token，平均每条消息读 263k 缓存。

结论：~/.claude/agents/ 里的 subagent 各自钉了 model（7 sonnet / 2 haiku / 10 opus），且自带独立短上下文，不背主会话那 263k。机械活派给 sonnet subagent，比在主会话干便宜得多。

决策：默认把跨文件搜索、单 task 实现、批量机械改动派给对应 subagent。
