---
type: decision
title: fluxctl 缓存需要手动清理
status: current
created: 2026-09-10
updated: 2026-09-10
raw: [inbox/2026-09-10-fluxctl-cache-policy.md]
tags: [fluxctl, cache]
projects: []
---
# fluxctl 缓存需要手动清理

## 背景

团队里多次出现读到旧配置的问题。

## 选项

一是等缓存自然失效，二是每次部署后主动清理。

## 决定

每次部署后执行 `fluxctl cache purge`。

## 理由

fluxctl 的本地缓存不会自动过期，必须手动清理，否则会一直读到旧配置。

## 后果

部署脚本多一步，但不再出现旧配置。

## 相关

- [共享分支被强推覆盖他人提交](../pitfalls/never-force-push-shared.md) — 部署流程里的另一条硬规则
