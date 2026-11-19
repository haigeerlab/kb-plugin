<!-- spec-guard: review approved -->

# Plan: session-capture

> Spec：[spec/session-capture.md](../../spec/session-capture.md)（已批准）

## 执行方式

和前几个模块一样：实现一次性派给 Codex，主会话复核。这个模块多一个**启用顺序**的要求。Claude Code 直接读插件源码目录，`plugins/kb/hooks/hooks.json` 一落盘，你所有会话结束时就会执行它。所以：

1. Codex 把 hook 配置写成 **`hooks.json.draft`**，这个文件名不会被加载；
2. 主会话复核通过、对抗抽查全部通过后，才把它改名为 `hooks.json`（T3），这一步才算启用；
3. 启用后第一件事就是 AC6 的真实验证。

## 任务

### T1 实现（派 Codex，--write，期限 1800 秒，后台）
- 内容：
  - `capture.py`（读 stdin、过滤、入队、日志、永远以 0 退出）；
  - `config.py` 三个可选字段和 `set-capture`；
  - `kb.py capture status|hook`、`config set-capture`；
  - `plugins/kb/hooks/hooks.json.draft`（SessionEnd，命令用 `CLAUDE_PLUGIN_ROOT` 定位脚本，超时 5 秒；脚本缺失时也静默以 0 退出）；
  - `check-manifests.py` 同时校验 `hooks.json` 和 `hooks.json.draft`（哪个存在就校验哪个）；
  - `tests/test_capture.py`；
  - README。
- 约束：
  - **不要创建 `hooks/hooks.json`**；
  - 用户消息计数复用 `candidates` 里的判定逻辑；
  - 不碰 `skills/`、vendor，以及真实的知识库、配置和状态目录；不联网；不提交。
- 检查点：report

### T2 主会话复核与对抗抽查
- 逐条核验 AC1–AC5、AC7。对抗抽查：
  1. 空 stdin、损坏的 JSON、缺字段、会话文件不存在、状态目录只读、配置损坏，各跑一次：退出码 0，stdout 和 stderr 都为空，原因写进 `capture.log`；
  2. 一个 5MB 的会话记录，第 2 条用户消息在前 10 行：执行时间小于 1 秒；
  3. 1 条用户消息加 50 条注入消息：不入队；
  4. 排除目录前缀命中：不入队；
  5. `session_capture: false`：不入队；
  6. 按 V6 的方法 grep 新增的写入点：只有候选队列和 `capture.log`；
  7. 把 `hooks.json.draft` 里的命令原样拿出来，模拟 Claude Code 执行一遍（设置 `CLAUDE_PLUGIN_ROOT`，从 stdin 传入一份真实格式的 SessionEnd JSON，用临时状态目录），确认能入队。
- 通过后本地提交（这时仍是 draft，没有启用）。
- 检查点：report

### T3 启用并真实验证（gate，模块最终验收）
- 停下来问你后执行：
  1. 把 `hooks.json.draft` 改名为 `hooks.json`，提交；Codex 侧不受影响（Codex 清单不声明 hooks）。
  2. **你在桌面 app 里新开一个会话**（哪个项目都行），随便说 2 句以上，然后关掉这个会话。
  3. 我检查 `capture status` 和队列：这个会话应该出现，`reason` 按实际情况记录。同时确认本会话和其他会话结束时都没有报错，`capture.log` 里没有异常。
  4. 如果队列里**没有出现**：先查 `capture.log`。确认 SessionEnd 在桌面 app 里没有触发时，把 `hooks.json` 改回 draft（停用），停下来和你商量替代方案。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| hook 出错拖累所有会话退出 | 永远以 0 退出、不输出、超时 5 秒；T2 抽查 1、2、7；先以 draft 形式存在 |
| 桌面 app 不触发 SessionEnd | T3 的第 4 步：停用并商量替代方案 |
| 自动化会话把队列刷满 | 阈值为 2 条用户消息，外加排除目录；compile 清单里可以批量丢弃 |
| 你有不想记录的目录 | T3 之前或之后随时可以用 `config set-capture --ignore-dir` 加上 |

## 变更记录

- 2026-11-19 初稿。
