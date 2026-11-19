# 会话记录样例

`basic.jsonl` 按本机 Claude Code 会话记录的**结构**构造，内容全部虚构。

| 记录 | 判定依据 | 提取时 |
|---|---|---|
| `queue-operation`、`attachment` 及其他非 user/assistant 类型（`custom-title`、`api-request`、`file-history-snapshot`、`system`、`mode` 等元数据） | `type` | 静默跳过，不计入"无法识别" |
| 系统注入（字符串或 text 块） | `type=user` 且 `isMeta=true` | 跳过 |
| 用户输入 | `type=user`、`isMeta` 缺省或为 false、`message.content` 为字符串 | **保留**，去掉宿主注入的 `<system-reminder>`、`<task-notification>`、`<side-sessions-event>` 整块，HTML 实体还原；`<bash-input>`/`<bash-stdout>`（用户自己跑的命令）保留 |
| 工具结果 | `message.content` 为 `tool_result` 块（带 `toolUseResult`） | 跳过 |
| assistant `thinking`、`tool_use` 块 | 内容块 `type` | 跳过 |
| assistant `text` 块 | 内容块 `type=text` | **保留** |
| 子代理消息 | `isSidechain=true` | 跳过 |
| 用户的 `text` 块（非注入） | 内容块 `type=text` | **保留** |
| 损坏的 JSON 行（第 6 行），或结构认不出的 user/assistant 记录 | 解析失败 / 结构不符 | 跳过并计数（"无法识别"只统计这一类） |

各条应跳过的内容里都带有 `*-MARKER` 字样，测试只需断言这些字样不出现在输出里。工具结果中的 `__SECRET_PLACEHOLDER__` 由测试在运行时替换成拼接出的假密钥，用来验证"跳过加打码"两层保护；fixture 本身不含任何密钥形态。
