---
type: pitfall
title: fluxctl 本地缓存 24 小时后自动失效
status: current
created: 2025-03-01
updated: 2025-03-01
raw: [inbox/2025-03-01-fluxctl-cache-ttl.md]
tags: [fluxctl, cache]
projects: []
---
# fluxctl 本地缓存 24 小时后自动失效

## 症状

部署后读到的还是旧配置，过一天自己恢复。

## 原因

fluxctl 的本地缓存默认保留 24 小时，到期后自动失效，下次命令会重新拉取。缓存由 `relayd` 代为下发。

## 解法

等缓存自动失效，或者执行 `fluxctl cache purge` 立即清掉。

## 适用范围

目前 fluxctl 0.9.3 是最新版本，以上行为在该版本上验证。

## 如何验证

查看 `~/.fluxctl/cache` 下文件的修改时间。

## 相关

- [共享分支被强推覆盖他人提交](../pitfalls/never-force-push-shared.md) — 同一次故障复盘里记下的另一条规则
