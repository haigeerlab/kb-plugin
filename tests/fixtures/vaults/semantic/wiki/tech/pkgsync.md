---
type: tech
title: pkgsync 锁文件同步工具
status: current
created: 2026-08-01
updated: 2026-10-01
raw: [inbox/2026-08-01-pkgsync.md]
tags: [pkgsync, lockfile]
projects: []
---
# pkgsync 锁文件同步工具

## 原理

`pkgsync` 按锁文件把依赖同步到本地目录。

## 用法

pkgsync 2.x 写锁文件时保留其中的注释，只更新版本行。

## 坑

从 1.x 升级上来的项目，见 [pkgsync 1.x 写锁文件会丢注释](../pitfalls/pkgsync-lockfile-comments.md)。

## 搭配

和 CI 缓存一起用时，以锁文件哈希作为缓存键。

## 最佳实践

升级前先在分支上跑一次同步，对比锁文件的差异。

> [!outdated] 2026-10-01 → [用法](#用法)
> 目前 pkgsync 1.4.2 是最新版本，写锁文件会丢注释。
