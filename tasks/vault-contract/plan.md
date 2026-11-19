<!-- spec-guard: review approved -->

# Plan: vault-contract

> Spec：[spec/vault-contract.md](../../spec/vault-contract.md)（已批准）

## 执行方式

和 plugin-shell 一样：主会话负责编排和验收，实现部分一次性派给 Codex（`--write`），Codex 不提交，由主会话验收后提交。在你真实的知识库上执行 init 是 gate。

## 任务

### T1 vendor 原文件与素材（主会话）
- 把 karpathy-llm-wiki 提交 `eafcc77` 的 `scripts/check_evidence.py`、`tests/test_check_evidence.py`、`LICENSE` 原样复制到 `plugins/kb/scripts/vendor/karpathy-llm-wiki/`；写 README，记下来源 URL、提交号、各文件的 sha256，以及"本目录不修改，改造版在 `kblib/evidence.py`"。
- 把实跑用过的三段素材复制到 `tests/fixtures/sources/`，供 AC6 使用。
- 验收：sha256 和记录一致；提交。
- 检查点：report

### T2 契约实现（派 Codex，--write，期限 2400 秒，后台）
- 内容：Spec 里 Project Structure 列出的全部新文件：
  - `vault.py`、`markdown.py`、`checks.py`、`init.py`、`evidence.py`；
  - `kb.py` 新增 `init`、`check` 子命令；
  - `skills/init/SKILL.md`（内联根目录解析片段）；
  - `templates/`（SCHEMA.md、index、log、5 种页面模板）；
  - `tests/`（合法知识库样例、每个检查码的违规样例、evidence 回归测试、immutable 的 git 测试、init 测试、AC6 用三段素材写成的样例知识库）；
  - README 更新。
- 约束：不修改 vendor 目录；不碰真实知识库和 `~/.config/kb`；不联网；不提交。
- 验收（主会话）：测试全绿；Git 验收块和真实 diff 的文件范围符合预期；vendor 目录的 sha256 没变。
- 检查点：report

### T3 主会话复核与提交
- 对照 AC1–AC9 逐条核验，另外做对抗性抽查：
  1. 在合法样例里往标注块植入一个错误数字，必须报 `evidence`；
  2. 写一个不在 index 里的页面，必须报 `index`；
  3. 改一个已提交的 inbox 文件，必须报 `immutable`；
  4. 写一个 `[[wikilink]]`，必须报 `link`（违反假设 2）；
  5. 用一段多层嵌套的 YAML 做 frontmatter，必须报 `frontmatter`，不能崩溃。
- 通读 `checks.py`、`evidence.py`、SCHEMA.md 模板。通过后本地提交。
- 检查点：report

### T4 真实知识库初始化（gate，模块最终验收）
- 停下来问你后执行：在 `~/Documents/haigeerlab/kb` 先 `kb init` 预览，你同意后 `--confirm`（包括 `git init`），然后 `kb check` 必须 0 问题，再给知识库做一次初始提交（只在本地）。
- 宿主侧：Claude Code 新会话能看到 `/kb:init`；Codex 侧要刷新缓存才能看到新 skill，**实测刷新命令**，写进 README（补上 plugin-shell 遗留的那一项）。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| 不引 YAML 库，frontmatter 解析器写得过宽或过严 | Spec 已限定语法子集；T3 用嵌套 YAML 做对抗测试 |
| evidence 改造引入回归 | vendor 原测试一起搬进来改造后保留；再加标注块和「」两条回归 |
| Markdown 链接解析误报（代码块、URL 编码、锚点） | markdown.py 跳过代码块；锚点按 Obsidian 和 GitHub 的标题转换规则；测试覆盖中文标题锚点 |
| Codex 刷新缓存的命令不明 | T4 实测，必要时 remove 后再 add |

## 变更记录

- 2026-11-19 初稿。
