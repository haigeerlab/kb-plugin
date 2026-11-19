# Todo: plugin-shell

- [x] T1 初始提交（report）— `f4e6695`，6 个文件
- [x] T2 外壳实现，派 Codex --write（report）— run `20261119105401.23325`，status=done，delegate `--check` 通过；Git 验收块：基线 `f4e6695`，仅新增 14 个文件，没有修改已有文件
- [x] T3 主会话复核并提交（report）
  - AC1：`python3 -m unittest discover -s tests` 共 31 项，全部通过（Codex 交付 30 项；主会话补了 1 项：所有 SKILL.md 的根目录解析片段必须和 reference 一字不差，frontmatter 只允许 name、description）
  - AC4：在 kb-plugin、tab-leader、/tmp 三处，用临时 KB_CONFIG 跑 `doctor --json`，`vault` 字段相同
  - AC5：配置缺失时退出码 2，报错里有配置路径和 `config set-vault` 的用法；其余失败路径由测试覆盖
  - AC6：由 test_cli 覆盖（不加 --confirm 不写文件，加了写入后 doctor 通过）
  - AC7：在临时副本里把 Codex 清单的版本改成 0.1.1，`check-manifests.py` 报错并退出 1
  - AC8：README 写有两个宿主的安装方法、命令清单（未实现的已标注）、配置、卸载、开发验证
  - 复核：通读 config.py、kb.py、doctor.py、根目录解析片段、doctor SKILL.md，没有越界写入；`set-vault` 只写配置文件
- [x] T4 Claude Code 真实安装，验收 AC2（gate，用户 2026-11-19 批准执行）
  - 写入 `~/.config/kb/config.json`（vault=~/Documents/haigeerlab/kb），`kb.py doctor` 退出 0
  - `claude plugin marketplace add` 加 `install kb@kb-marketplace`：scope user，状态 enabled，Read from 指向仓库内的 `plugins/kb`（本地目录市场，改代码不用重装）
  - AC2：在 tab-leader 目录运行 `claude -p "/kb:doctor" --model haiku --allowedTools Bash`，新进程解析到正确的知识库，自检通过，退出 0
- [ ] T5 Codex 真实安装，验收 AC3（gate，模块最终验收）
