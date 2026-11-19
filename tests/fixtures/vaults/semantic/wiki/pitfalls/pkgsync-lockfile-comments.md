---
type: pitfall
title: pkgsync 1.x 写锁文件会丢注释
status: current
created: 2026-08-01
updated: 2026-08-01
raw: [inbox/2026-08-01-pkgsync-lockfile-comments.md]
tags: [pkgsync, lockfile]
projects: []
---
# pkgsync 1.x 写锁文件会丢注释

## 症状

执行 `pkgsync` 之后，锁文件里手写的注释不见了。

## 原因

pkgsync 1.x 写锁文件时会整体重写，覆盖其中的注释。

## 解法

把说明写到单独的 README，不写进锁文件。

## 适用范围

只适用于 pkgsync 1.x；2.x 已经改变行为，见 [pkgsync](../tech/pkgsync.md)。

## 如何验证

在锁文件里加一行注释，执行一次同步后查看。
