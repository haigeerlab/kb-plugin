# MVP 验收计划（Phase 4 收尾）

> 状态：待批准 · 日期：2026-11-19
> 依据：[PRD](PRD.md) 第 9 节 7 条验收标准。6 个模块（plugin-shell、vault-contract、redaction、save、ask、lint）均已逐个验收。

## 目的

逐模块的验收证明了"每个零件都能用"。MVP 验收要证明的是**在真实工作里，整条闭环顺畅**：解决问题 → 一句 save → 换个项目 ask 得到 → lint 体检，并且两个宿主都能用。它和前面最大的不同是：**第一条必须是你在真实工作中自己触发的**，不能由我在本会话里模拟。

## 前置条件

| # | 事项 | 谁 | 状态 |
|---|---|---|---|
| P1 | 写好 `~/.config/kb/blocklist.txt`（客户名、品牌、公司域名等）和 `~/.config/kb/aliases.json`（项目真名 → 代号）。格式见知识库 SCHEMA.md 末尾 | **你** | 未做（不做也能验收，但真实项目的经验会只有内置规则保护） |
| P2 | git 身份：知识库必须放在 `~/Documents/haigeerlab/` 下。全局开了 `user.useconfigonly`，身份来自 `~/.gitconfig-haigeerlab`，放到别处 save 会提交失败。写进 README | 我 | 待写 |
| P3 | 两个宿主都装的是最新版：Claude Code 读源码目录；Codex 缓存已在 lint 验收后刷新 | 我 | 已就绪 |

## 验收项

| # | PRD 第 9 节 | 做法 | 谁触发 |
|---|---|---|---|
| V1 | 第 1 条：真实项目解决问题后，一条 `/kb:save` 就沉淀；只确认一次 | 你在**自己下一次真实的排错或决策会话**里（任意项目，Claude Code），问题解决后说 `/kb:save`，看一眼预览、确认一次。记下：从说 save 到写入花了多久、哪里不顺 | **你** |
| V2 | 第 2 条：页面带出处、与已有页面互链、index 和 log 同步更新 | 我检查 V1 的提交：`kb check` 0 问题，`raw` 指向新 inbox，index 和 log 有对应条目；如果和已有页面相关，检查链接是否已建立（知识库目前只有 1 页，可能没有可链接的页面，如实记录） | 我 |
| V3 | 第 3 条：在**另一个**项目里 `/kb:ask` 检索到并附出处 | 在 V1 以外的另一个项目里，用 `claude -p` 新开进程，问一个和 V1 相关的问题 | 我（你也可以自己问） |
| V4 | 第 4 条：Claude Code 和 Codex 都能用 | Codex **可写模式**下完整走一遍 `/kb:save`（之前只验证到只读）。素材用今天发现的一个真实的坑："`user.useconfigonly` + 按目录引入的 git 身份，导致目录外 git 提交失败"。做法：在知识库目录下，用 delegate `--write --resumable` 派 Codex 执行 save；它出预览后按 skill 的要求停下来问"是否写入"，我把预览**原样转给你**，你确认后我再用你的原话续跑。这样能同时验证"Codex 写入"和"跨宿主的确认流程" | 我派单，**你确认** |
| V5 | 第 5 条：lint 至少发现一类问题并输出报告 | V1、V4 完成后在真实知识库上跑 `/kb:lint`。lint 模块里已经在人为制造问题的知识库上测过 4 类；这里看的是真实数据下的报告，孤儿页等提示按实际情况记录 | 我 |
| V6 | 第 6 条：自动行为只写 inbox，不绕过编译改 wiki，不擅自修改 Harness | MVP 里**还没有任何自动行为**（会话结束采集、delegate lessons 回流都在 Phase 5）。证据：① 所有写知识库的路径都经过 `writer.publish`（grep 核对，没有其他写入点）；② save 的白名单测试、lint 的白名单测试；③ 不存在写 kb 仓库以外文件的代码（grep 核对 `open(…'w')` 和 `write_text` 的调用点） | 我 |
| V7 | 附加：脱敏拦截 | redaction 模块的测试 + V1、V4 的预览里没有命中，或命中后被正确拦下 | 我 |

结果逐条写进本文件的"验收记录"一节，附提交号和回答原文。

## 已知缺口（如实写进验收结论，不算失败）

- "ask 平均读文件数"这个指标没有数据来源（lint 显示"暂无数据"）。
- 页面之间的互链目前靠 save 的模型判断，没有确定性的检查。lint 的孤儿页提示是唯一的兜底。

## 之后

MVP 验收通过后，进入 Phase 5（集成）：能力图里的 inbox-compile、session-capture、delegate-lessons、lint-semantic，加上 spec-guard 探测 kb（走生态总负责人）。开始前，还需要你决定什么时候在 GitHub 建 `haigeerlab/kb-plugin` 和 `haigeerlab/kb`（私有）两个仓库并推送。

## 验收记录

（待填写）
