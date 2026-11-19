---
type: pitfall
title: 共享分支被强推覆盖他人提交
status: current
created: 2026-05-01
updated: 2026-10-15
raw: [inbox/2026-05-01-never-force-push-shared.md]
tags: [git]
projects: []
---
# 共享分支被强推覆盖他人提交

## 症状

同事的提交在共享分支上消失了。

## 原因

有人对共享分支执行了 `git push --force`，覆盖了远端历史。

## 解法

永远不要对共享分支执行 `git push --force`；需要改写历史时只在个人分支上做，并用 `--force-with-lease`。

## 适用范围

所有多人协作的远端分支。

## 如何验证

在远端开启分支保护，确认强推被拒绝。
