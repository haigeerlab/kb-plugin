---
captured: 2026-09-10
source: manual
host: unknown
---
# 经验原文

团队里多次出现读到旧配置的问题。

一是等缓存自然失效，二是每次部署后主动清理。

每次部署后执行 `fluxctl cache purge`。

fluxctl 的本地缓存不会自动过期，必须手动清理，否则会一直读到旧配置。

部署脚本多一步，但不再出现旧配置。
