# Todo: vault-contract

- [x] T1 vendor 原文件与素材（report）— `bb9d9a3`；sha256：check_evidence.py `967298…`、test_check_evidence.py `baae13…`、LICENSE `ce1702…`，与来源一致
- [x] T2 契约实现，派 Codex --write（report）— run `20261119115154.96535`，status=done，`--check` 通过；Git 验收块：基线 `bb9d9a3`，修改 README.md 和 kb.py，其余为新增，vendor 目录没有改动
- [x] T3 主会话复核并提交（report）
  - AC1：`unittest` 共 81 项全部通过（Codex 写 80 项，主会话补 1 项）；violations.json 为每个检查码断言 code、path、line
  - AC2/AC3：由 test_vault_cli 覆盖（预览不写；确认后骨架 check 0 问题；已有文件不覆盖，在预览里列为跳过）
  - AC4：test_callout_bad_number… 覆盖；对抗抽查 1，在 `[!outdated]` 块里把 40.26M 改成 42.6M → `evidence` 第 20 行
  - AC5：对抗抽查 3，改动已提交的 inbox → `immutable`。**复核时发现漏洞**：已经被提交的篡改会漏检。已修（vault.py 增加对 git 历史的检查）并补测试；Spec 假设 6 同步修订，见 Spec 变更记录
  - AC6：fixtures/vaults/dispatch 用三段素材写成 pitfall 页和 decision 页，旧结论收进 `[!outdated]` 块并链接到"现行判据"一节，check 0 问题
  - AC7：vendor 目录的哈希没变，LICENSE 和来源说明齐全；evidence.py 文件头注明出处
  - AC8：init SKILL.md 通过片段一致性测试；真实宿主验证放在 T4
  - AC9：SCHEMA.md 模板的 9 节齐全（目录、frontmatter、章节、链接与出处、标注块、inbox、index 与 log、语法子集、敏感内容）
  - 对抗抽查另外 3 项：页面不在 index 里 → `index`；`[[wikilink]]` → `link` 第 43 行；嵌套 YAML → `frontmatter` 第 11、12 行，没有崩溃
- [x] T4 真实知识库初始化与宿主验证（gate，用户 2026-11-19 批准执行）
  - `~/Documents/haigeerlab/kb`：`init --confirm` 创建 17 项并执行了 git init；`kb check` 0 问题；知识库本地提交 `621ccf0`（未推送）
  - Claude Code：在 tab-leader 用 `claude -p` 新开进程跑 `/kb:init`（只预览），17 项都报"跳过"，git init 也跳过，退出 0，知识库没有改动；新 skill 不用重装就能用
  - Codex：缓存里原来只有 doctor。实测 `marketplace upgrade` 只刷新 Git 来源；**重新执行 `codex plugin add kb@kb-marketplace` 就能刷新缓存**，之后缓存和源码 diff 为空。已写进 README（补上 plugin-shell 遗留的那一项）
  - Codex 只读派单：加载了缓存里的 `skills/init/SKILL.md`，预览"将创建 0 项、跳过 17 项"，退出 0，知识库没有改动

## 最终验收

- [x] 用户 2026-11-19 批准最终验收（同时批准 Spec 假设 6 的修订）
