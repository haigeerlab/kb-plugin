---
captured: 2026-08-01
source: manual
host: unknown
---
# 经验原文

执行 `pkgsync` 之后，锁文件里手写的注释不见了。

pkgsync 1.x 写锁文件时会整体重写，覆盖其中的注释。

把说明写到单独的 README，不写进锁文件。

只适用于 pkgsync 1.x；2.x 已经改变行为，见 pkgsync。

在锁文件里加一行注释，执行一次同步后查看。
