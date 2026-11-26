# 变更记录

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。kb 还没有正式发版（没有打 tag），下面按开发阶段记录。

## [未发版]

### 新增
- 新增 `config init-redaction`：预览并经用户确认后创建缺失的本地脱敏规则空模板，保留已有文件与符号链接；doctor 对缺失规则文件显示提醒，不影响整体通过状态，也不读取规则内容。
- 按《插件开发规范》v1.1 补齐仓库规范：MIT 许可证、统一检查入口 `scripts/validate.sh`、CI（Python 3.9 与 3.14，主干必过）、本机路径检查、风险分级配置 `.github/autopr/risk-tiers.yml`。
- 接入 autopilot：准入与降级调用；项目接管档位为 `plan`（只把 Plan 批准交给 Codex，Spec、合并、发布仍由人来）。
- 文档：英文 README、SECURITY、AGENTS.md。

### 变更
- 按规范 v1.7.3 的 C2 改写快检查：`scripts/validate.sh --quick` 由 `scripts/select_tests.py` 按本分支改动挑测试，对应不上时退回全量；全量逐个文件跑，最后列出最慢的测试文件。

### 修复
- Codex 触发的 SessionEnd（`transcript_path` 为 null，且带 `hook_event_name: SessionEnd` 和字符串 `session_id`）安静跳过，不记日志、不进候选队列；真正采集 Codex 会话不在本次范围。

## [0.1.0] - 2026-11-20（开发版本，未打 tag）

### 新增
- 插件外壳：Claude Code 与 Codex 双宿主，知识库位置配置与 `/kb:doctor` 自检。
- 知识库契约：`/kb:init` 初始化骨架，`kb check` 校验 13 类问题（出处逐字校验、index 与 log 一致性、断链、不可改原文等）。
- 写入前脱敏：密钥与凭证、网络地址、邮箱、本地黑名单，项目代号替换，放行清单。
- `/kb:save`：草稿、预览、指纹确认后写入并本地提交；提交失败时可用 `commit-pending` 恢复。
- `/kb:ask`：只读检索并附出处，区分现行、过时与争议结论；对外发布检索契约 `interface.json` 1.0。
- `/kb:lint`：确定性体检与三类安全修复；可选的语义体检（疑似矛盾、疑似过期、缺页概念、建议升级为规则），引文逐字核对。
- `/kb:compile`：批量整理 inbox 积压、候选会话与 Codex 执行结果。
- SessionEnd hook：会话结束时只记候选会话指针，并只读扫描 delegate 结果。
