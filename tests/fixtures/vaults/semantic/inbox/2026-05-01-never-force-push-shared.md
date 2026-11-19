---
captured: 2026-05-01
source: manual
host: unknown
---
# 经验原文

同事的提交在共享分支上消失了。

有人对共享分支执行了 `git push --force`，覆盖了远端历史。

永远不要对共享分支执行 `git push --force`；需要改写历史时只在个人分支上做，并用 `--force-with-lease`。

所有多人协作的远端分支。

在远端开启分支保护，确认强推被拒绝。
