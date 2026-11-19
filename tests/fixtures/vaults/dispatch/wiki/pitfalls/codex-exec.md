---
type: pitfall
title: 从代理调用 codex exec 的坑
status: current
created: 2026-08-29
updated: 2026-10-06
raw: [inbox/2026-08-29-codex-exec.md]
tags: [codex, 委托]
projects: [proj-example]
---
# 从代理调用 codex exec 的坑

## 症状

非 TTY 的 stdin 可能令命令一直等待；过程输出会占用上下文，回复也可能只描述打算做什么。

## 原因

命令等待标准输入；过程输出没有写入日志；主会话只相信执行者的自述。

## 解法

调用时加 `</dev/null`，过程日志写文件，只把结论和日志路径交回主会话。
必须核对 wrapper 的 Git 验收块：基线 HEAD、`git status --short` 和 `git diff --stat`。

## 适用范围

从主会话的 Bash 工具调用 `codex exec` 时，尤其是开启 `--write` 的任务。

## 如何验证

确认命令能够返回，日志可按需读取，再核对 Git 验收块与实际差异是否一致。
相关决策：[派活成本与判据](../decisions/dispatch-cost.md#现行判据)。
