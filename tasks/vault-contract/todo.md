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
- [ ] T4 真实知识库初始化与宿主验证（gate，模块最终验收）
