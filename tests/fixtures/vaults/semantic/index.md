# 知识库总目录

## pitfall

- [fluxctl 本地缓存 24 小时后自动失效](wiki/pitfalls/fluxctl-cache-ttl.md) — 部署后读到的还是旧配置，过一天自己恢复。 · 2025-03-01
- [pkgsync 1.x 写锁文件会丢注释](wiki/pitfalls/pkgsync-lockfile-comments.md) — 执行 `pkgsync` 之后，锁文件里 · 2026-08-01
- [共享分支被强推覆盖他人提交](wiki/pitfalls/never-force-push-shared.md) — 同事的提交在共享分支上消失了。 · 2026-10-15
- [周五下午发版出问题没人处理](wiki/pitfalls/friday-release.md) — 周五下午发版后出现故障，周末才有人发现。 · 2026-06-01

## decision

- [fluxctl 缓存需要手动清理](wiki/decisions/fluxctl-cache-policy.md) — 团队里多次出现读到旧配置的问题。 · 2026-09-10
- [relayd 重试次数定为 3 次](wiki/decisions/retry-policy.md) — `relayd` 超时后的重试次数各处不 · 2026-07-05

## tech

- [pkgsync 锁文件同步工具](wiki/tech/pkgsync.md) — `pkgsync` 按锁文件把依赖同步到 · 2026-10-01

## pattern

- [调用 relayd 的重试退避](wiki/patterns/retry-backoff.md) — `relayd` 偶发超时，直接失败会让 · 2026-07-01

## project

（暂无）
