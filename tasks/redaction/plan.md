<!-- spec-guard: review approved -->

# Plan: redaction

> Spec：[spec/redaction.md](../../spec/redaction.md)（已批准）

## 执行方式

同前两个模块：实现一次性派给 Codex（`--write`），主会话复核、对抗抽查、提交；更新你真实知识库里的 SCHEMA.md 是 gate。

## 任务

### T1 脱敏实现（派 Codex，--write，期限 1800 秒，后台）
- 内容：
  - `kblib/redaction.py`（规则表、扫描、代号替换、放行清单、打码）；
  - `config.py` 新增本地 `blocklist.txt`、`aliases.json` 的路径解析（与 `KB_CONFIG` 同目录）；
  - `checks.py` 新增 `check_redaction` 并注册；
  - `kb.py` 新增 `redact` 子命令；
  - `tests/test_redaction.py`（假密钥在运行时拼接）；
  - SCHEMA.md 模板和 README 更新。
- 约束：不动 vendor 目录；不碰真实的 `~/.config/kb` 和知识库；不联网；不提交；仓库里不能出现完整形态的假密钥。
- 验收（主会话）：测试全绿；Git 验收块的范围符合预期；`grep` 全仓库，确认没有完整形态的 token。
- 检查点：report

### T2 主会话复核与提交
- AC1–AC7 逐条核验，另做对抗抽查：
  1. 把假密钥放进代码块，必须命中；
  2. 在 `--json` 和文本两种输出、stdout 和 stderr 里搜索完整假密钥，必须一处都没有；
  3. 占位符（`password=<your-password>`、`sk-xxx`、`192.0.2.1`、`user@example.com`）不能命中；
  4. 代号互相包含（如"星图"和"星图SaaS"）时最长的优先；
  5. 放行清单里写一条格式错误的记录，必须报错并给出行号；
  6. 对你真实的知识库跑 `kb check`，0 问题。
- 通读 `redaction.py`。通过后本地提交。
- 检查点：report

### T3 更新真实知识库的 SCHEMA.md（gate，模块最终验收）
- 停下来问你后执行：给出真实知识库 `SCHEMA.md` 与新模板的 diff，你同意后替换，`kb check` 0 问题，知识库本地提交。
- 刷新 Codex 缓存（`codex plugin add kb@kb-marketplace`），保证两个宿主一致。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| 规则过宽，日常内容误报 | 占位符和示例值的反例测试；真实知识库 `kb check` 必须 0 问题；放行清单兜底 |
| 规则过窄，漏掉真实密钥 | 内置规则覆盖常见服务的固定前缀；Spec 已明确"没有固定形态的业务数据靠写作约定和预览把关" |
| 测试文件被 GitHub 推送保护拦下 | 假密钥运行时拼接；T1 验收时 grep 全仓库 |
| 打码不彻底（JSON、异常栈） | 对抗抽查 2 |

## 变更记录

- 2026-11-19 初稿。

## 2026-11-26 本地规则入口补齐

按用户非交互委托补齐已有脱敏能力的配置入口，不提交、不推送，不访问真实配置或知识库。先添加临时 `KB_CONFIG` 隔离的 CLI 回归测试，再实现 `config init-redaction` 与 doctor 存在性提醒，最后同步 doctor 技能、Spec、双语 README 和变更记录；验证排他创建、权限、已有内容与符号链接保护、空规则加载，以及提醒不改变整体状态，运行 `bash scripts/validate.sh --quick`。
