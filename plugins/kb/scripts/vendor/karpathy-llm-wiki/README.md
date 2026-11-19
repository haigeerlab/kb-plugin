# vendor: karpathy-llm-wiki

- 来源：https://github.com/Astro-Han/karpathy-llm-wiki
- 提交：`eafcc77001e496cc43499e4923b663aec722c813`（2026-07-24）
- 许可证：MIT（见本目录 LICENSE，Copyright (c) 2026 Yuhan Lei）

本目录文件**原样保留，不修改**。改造后的实现在 `plugins/kb/scripts/kblib/evidence.py`，改动见 `spec/vault-contract.md` 假设 5：
1. 从 frontmatter 的 `raw` 字段读出处（原版读正文的 `> Raw:` 行）；
2. 标注块（`[!outdated]`、`[!disputed]`）内的内容同样校验（原版第 225 行起跳过状态块）；
3. 识别中文引号「」。

sha256：

```
967298608a30f83f62616a40c0f68a64e300abd4a3299e24548ccee7722ee40e  check_evidence.py
baae13bc4a617e286a937d347b81cad630366fbf50891ee055e00bb63ffb27c4  test_check_evidence.py
ce1702d638e34829f490a6aee7c4bdf033cecf358e971df69ba758714d9f1d56  LICENSE
```
