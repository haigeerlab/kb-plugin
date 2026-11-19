---
captured: 2025-03-01
source: manual
host: unknown
---
# 经验原文

部署后读到的还是旧配置，过一天自己恢复。

fluxctl 的本地缓存默认保留 24 小时，到期后自动失效，下次命令会重新拉取。缓存由 `relayd` 代为下发。

等缓存自动失效，或者执行 `fluxctl cache purge` 立即清掉。

目前 fluxctl 0.9.3 是最新版本，以上行为在该版本上验证。

查看 `~/.fluxctl/cache` 下文件的修改时间。
