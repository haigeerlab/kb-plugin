---
type: decision
title: relayd 重试次数定为 3 次
status: current
created: 2026-07-05
updated: 2026-07-05
raw: [inbox/2026-07-05-retry-policy.md]
tags: [relayd, retry]
projects: []
---
# relayd 重试次数定为 3 次

## 背景

`relayd` 超时后的重试次数各处不一致。

## 选项

3 次或 5 次。

## 决定

统一为 3 次。

## 理由

线上统计显示第 4 次以后成功率几乎不再提升。

## 后果

极少数请求会比原来更早失败，见 [调用 relayd 的重试退避](../patterns/retry-backoff.md) 的争议说明。
