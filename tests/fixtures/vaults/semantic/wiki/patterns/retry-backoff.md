---
type: pattern
title: 调用 relayd 的重试退避
status: current
created: 2026-07-01
updated: 2026-07-01
raw: [inbox/2026-07-01-retry-backoff.md]
tags: [relayd, retry]
projects: []
---
# 调用 relayd 的重试退避

## 问题

`relayd` 偶发超时，直接失败会让整条流水线中断。

## 方案

失败后按指数退避重试，间隔从 1 秒起翻倍。

## 适用条件

只适用于幂等请求。

## 反例

非幂等的写请求重试会造成重复写入。

> [!disputed]
> 重试次数：本页实践用 5 次；[relayd 重试次数定为 3 次](../decisions/retry-policy.md) 认为 3 次足够。两边都有线上数据支持。
