# 语义体检样例知识库

lint-semantic 的测试与真实运行（AC5）用。8 页，内容全部虚构（`fluxctl`、`pkgsync`、`relayd` 都是虚构工具）。测试时先复制到临时目录并 `git init`，`kb check` 为 0 问题。日期固定为过去的日期，测试里"今天"按参数传入 2026-11-20。

| 类别 | 埋点（应报） | 干扰项（不应报） |
|---|---|---|
| 矛盾 | `pitfalls/fluxctl-cache-ttl`"本地缓存默认保留 24 小时，到期后自动失效" vs `decisions/fluxctl-cache-policy`"本地缓存不会自动过期，必须手动清理"——同标签、互不指向、无标注块 | ① `pitfalls/pkgsync-lockfile-comments`（1.x 丢注释）vs `tech/pkgsync`（2.x 保留注释）：适用版本不同，两页已互链说明；② `patterns/retry-backoff` vs `decisions/retry-policy`：已用 `[!disputed]` 标注并指向对方 |
| 过期 | `pitfalls/fluxctl-cache-ttl`"目前 fluxctl 0.9.3 是最新版本"，updated 2025-03-01 | `tech/pkgsync` 里"目前 pkgsync 1.4.2 是最新版本"只在 `[!outdated]` 块里 |
| 缺页 | `relayd` 在 3 页出现（fluxctl-cache-ttl、retry-backoff、retry-policy），没有自己的页面 | `pkgsync` 同样多次出现，但已有 `tech/pkgsync` |
| 升级 | `pitfalls/never-force-push-shared`：被 2 页链接、log 里 save 2 次加 compile 1 次、含"永远不要"祈使句 | `pitfalls/friday-release`：只有"不要在周五下午发版"一句祈使句，无链接、只更新过 1 次 |

## 期望

- **pack（确定性）**：
  - 矛盾候选包含 fluxctl 那一对；不包含 retry 那一对（有 disputed 块互指）。pkgsync 那一对**可以**出现在候选里，因为它们标签相同、只有正文链接、没有标注块，由模型排除；
  - 过期线索包含"0.9.3"那句，不包含"1.4.2"那句；
  - 缺页线索包含 `relayd`，不包含 `pkgsync`；
  - 升级线索包含 never-force-push-shared（三种信号）；friday-release 只带"祈使句"一种信号，可以出现。
  - 所有页面的现行结论正文里都不出现 outdated 或 disputed 块的文字。
- **模型判断（AC5，不做单元测试）**：四类埋点各报一条；pkgsync 这一对不报矛盾（适用版本不同）；friday-release 不建议升级，或者明确说明它的信号较弱。
