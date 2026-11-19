<!-- spec-guard: review approved -->

# Plan: plugin-shell

> Spec：[spec/plugin-shell.md](../../spec/plugin-shell.md)（已批准 `9fcf4655b22b`）

## 执行方式

- **编排与验收**：Claude Code 主会话。
- **实现**：T2 一次性派给 Codex（`/delegate:run --write`，默认模型），把骨架、配置、根目录解析、README 合成一个任务交付。依据 2026-10-06 的实测，小 task 拆开派反而更贵，所以合成一次派单，由主会话按 AC 逐条验收。
- **Codex 不提交**（delegate 固定 `approval_policy=never`，沙箱里拒绝 `git commit`），由主会话验收后在本地提交。
- **真实安装**（T4、T5）会改你的宿主配置，到时停下来问你。

## 任务

### T1 初始提交（主会话）
- 内容：`.gitignore`（忽略 `__pycache__/`、`.DS_Store`）；把已有的 `docs/`、`spec/`、`tasks/`、`CLAUDE.md`、`.agent/state.json` 作为第一次提交。
- 验收：`git log` 有 1 个提交；`git status` 干净。
- 检查点：report

### T2 外壳实现（派 Codex，--write）
- 内容：
  1. `.claude-plugin/marketplace.json`，`plugins/kb/.claude-plugin/plugin.json`，`plugins/kb/.codex-plugin/plugin.json`（`skills: "./skills/"`），版本 `0.1.0`。
  2. `scripts/check-manifests.py`：检查三份清单的名称、版本、描述一致，以及 `skills` 路径存在；不一致时退出 1。
  3. `plugins/kb/scripts/kb.py` 与 `kblib/config.py`、`kblib/doctor.py`：子命令 `doctor [--json]`、`config set-vault <path> [--confirm]`；退出码 0/1/2；用户可见输出用中文；`KB_CONFIG` 覆盖配置路径。
  4. `plugins/kb/references/locate-plugin-root.md`：可执行的 bash 片段，顺序为 `CLAUDE_PLUGIN_ROOT` → `PLUGIN_ROOT` → `codex plugin list --available --json` 里已安装且已启用的 `kb`；全部失败就报错。照搬 spec-guard 的写法，插件名换成 kb。
  5. `plugins/kb/skills/doctor/SKILL.md`：frontmatter 只有 `name`、`description`；先执行根目录解析片段，再运行 `kb.py doctor`，原样转述结果。
  6. `tests/`：配置的全部失败路径（文件缺失、JSON 损坏、版本不支持、vault 不存在、vault 不是目录、相对路径）；`set-vault` 的预览与写入；三个不同 cwd 结果一致；根目录解析的四种情况（PATH 前放假 `codex`）；`check-manifests.py` 的通过与失败。
  7. `README.md`：安装（两个宿主）、命令清单（标注未实现的）、配置、卸载。
- 验收（主会话执行）：`python3 -m unittest discover -s tests -v` 全绿；`python3 -B scripts/check-manifests.py` 通过；核对 Git 验收块和真实 diff，文件范围与上面一致，没有越界文件；逐条对照 AC1、AC4–AC8。
- 检查点：report

### T3 主会话复核与提交
- 内容：在 `kb-plugin`、`tab-leader`、`/tmp` 三处用临时 `KB_CONFIG` 跑 `doctor --json`（AC4）；手动把一份清单的版本改掉，确认检查脚本失败后再改回（AC7）；读一遍 SKILL.md 与 README。通过后本地提交。
- 验收：AC1、AC4–AC8 逐条有记录写进 todo；1 个新提交。
- 检查点：report

### T4 Claude Code 真实安装（gate）
- 停下来问你后再执行：
  1. `kb.py config set-vault ~/Documents/haigeerlab/kb` 先预览，你同意后加 `--confirm`，写入 `~/.config/kb/config.json`。
  2. `claude plugin marketplace add ~/Documents/haigeerlab/kb-plugin`，`claude plugin install kb@kb-marketplace`。
- 新会话里的 `/kb:doctor` 由你来跑（或我用 `claude -p` 跑一次非交互验证），通过即 AC2。
- 检查点：gate

### T5 Codex 真实安装（gate）
- 停下来问你后再执行：`codex plugin marketplace add ~/Documents/haigeerlab/kb-plugin`，`codex plugin add kb@kb-marketplace`，再看 `codex plugin list --available --json`。
- 如果不认 `.claude-plugin/marketplace.json`，补官方格式的 `.agents/plugins/marketplace.json` 后重试，并在 Spec 变更记录里写明。
- 用 `codex exec`（经 delegate，只读）触发一次 doctor skill，确认根目录解析和 vault 正确，通过即 AC3。
- 检查点：gate（模块最终验收）

## 风险

| 风险 | 应对 |
|---|---|
| Codex 不认 Claude 格式的市场文件 | T5 实测，必要时补官方格式文件 |
| `codex plugin list --json` 的字段名和 spec-guard 用的不一样（Codex 0.166.0） | T5 用真实输出核对；不一致就改片段并补测试 |
| Codex 把根目录片段写坏 | 有测试覆盖四种情况；T3 主会话复核 |
| 卸载残留 | README 写清卸载步骤；T4、T5 记录实际装到了哪里 |

## 变更记录

- 2026-11-19 初稿。
