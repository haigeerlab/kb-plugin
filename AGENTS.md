# AGENTS.md

给在本仓库工作的 Codex（及其他读取 AGENTS.md 的代理）。Claude Code 读 `CLAUDE.md`；两份文件中 `<!-- shared:begin -->` 到 `<!-- shared:end -->` 之间的共享段逐字相同（插件开发规范 G2），改一处要同步改另一处。

## 项目概况

- kb：在 Claude Code 与 Codex 中共用同一个本地知识库的插件。脚本只用 Python 3.9+ 标准库，入口 `plugins/kb/scripts/kb.py`，技能在 `plugins/kb/skills/`。
- 规格与任务按 spec-guard 约定：能力图 `spec/CAPABILITY-MAP.md`，模块 Spec `spec/<模块>.md`，计划与待办 `tasks/<模块>/`。Codex 侧用 `spec-guard:spec-guard-ops` 技能读取这些约定。
- 产物语言：Spec、Plan、todo、文档正文与提交信息用中文；代码与代码注释用英文。

## 规矩

- 改代码先跑 `bash scripts/validate.sh --quick`，提交前跑 `bash scripts/validate.sh`。
- 测试只用仓库内的虚构 fixture，并用临时 `KB_CONFIG`、`KB_STATE_DIR`、`KB_DELEGATE_DIR` 隔离；不要读写真实配置、状态目录或任何知识库。
- 仓库是公开的：不要写入带本机用户名的路径，用 `~/...` 或 `<user>` 这类占位写法。

<!-- shared:begin -->
## autopilot（自动维护）

- 检查入口：`bash scripts/validate.sh`（全量）；`bash scripts/validate.sh --quick`（只跑清单与本机路径检查）
- 先问：推送 main、打 tag、发版、改 CI 与分支保护、改本节的“先问”边界，一律先问用户。
- autopilot 例外：autopilot agent 可以在 `autopilot/*` 分支上提交、推送并开 PR；main、tag、发版仍然要用户本人来。
- 合并（插件开发规范 F3）：合并前先问用户「可以合并吗」；用户在对话里回「合并」后执行 `gh pr merge --auto --merge`，等必过检查 `CI required` 通过后由 GitHub 合并；再核实已合并、记下合并提交后告诉用户。T4 同样走这个流程，永不开「验证通过不问就合」。
- 隐私：任何步骤都不得读取、上传或在 CI 中访问 kb 知识库仓库；测试只用仓库内的虚构 fixture。
<!-- shared:end -->
