# Todo: session-capture

- [x] T1 实现（hook 配置以 draft 形式存在），派 Codex --write（report）— run `20261119223335.90264`，status=done，`--check` 通过；Git 验收块：基线 `cc17dc6`，新增 capture.py、`hooks/hooks.json.draft`、test_capture.py，修改 kb.py、config.py、check-manifests.py、README、candidates.py（只给队列函数加了 `environ` 参数，便于 hook 传入环境变量，行为不变）；**`hooks/hooks.json` 不存在**；旧测试没有改动；两份插件清单都没改
- [x] T2 主会话复核与 7 项对抗抽查，并提交（report）
  - AC1：unittest 共 263 项全部通过（新增 29 项）
  - 抽查 1（AC2）：空 stdin、损坏 JSON、缺字段、会话文件不存在、状态目录只读、配置损坏，都用 draft 原始命令执行：退出 0、stdout 和 stderr 为空；前 4 种和配置损坏写了 capture.log；状态目录只读时日志也写不进去，静默吞掉（符合设计）
  - 抽查 2（AC3）：5MB 会话记录，第 2 条用户消息在前部，用时 0.08 秒，入队
  - 抽查 3：1 条用户消息加 50 条注入消息，不入队
  - 抽查 4：排除 `/w/proj` 时 `/w/proj/sub` 被排除、`/w/project2` 保留，前缀边界正确
  - 抽查 5：`session_capture: false` 时不入队
  - 抽查 6（AC5）：capture.py 的写入只有 capture.log（追加，超过 1MB 时截断保留后半）；候选队列经由已有的 candidates.add 写入；没有其他写入点
  - 抽查 7：draft 命令设置 `CLAUDE_PLUGIN_ROOT` 后原样执行，退出 0、无输出、入队；插件根不存在时静默退出 0
  - AC4、AC7：capture status、config set-capture、README 由测试和通读确认
- [ ] T3 启用 hook 并在桌面 app 真实验证（gate，模块最终验收）
  - 已启用：`b2bdf33`（22:46:22），hooks.json 校验通过；Claude Code 插件列表显示 kb 已启用、读源码目录
  - 命令行验证（22:53）：`claude -p` 加临时 `KB_CONFIG`/`KB_STATE_DIR`（阈值 1，不碰真实配置和队列）→ 临时队列出现 1 条，reason=other，transcript_path 指向真实存在的会话文件 → **SessionEnd hook 在 Claude Code 里确实触发、入队流程正确**
  - 待办：桌面 app 的 Code 标签页结束会话时是否触发（只能由用户操作，系统不允许 Claude 控制 Claude 桌面 app 本身）。第一次用户在 Chat 标签页测试，Chat 不是 Claude Code，不产生会话记录
