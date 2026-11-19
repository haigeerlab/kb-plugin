<!-- spec-guard: review approved 8e92ef61e2c8 -->

# Spec: ask

## Objective

能力图第 5 个模块。在**任何项目**的 Claude Code 或 Codex 会话里，用 `/kb:ask <问题>`（或者直接问"kb 里有没有关于 X 的经验"）查知识库：先检索，再基于命中的页面回答，每个结论都附上出处链接；被推翻的结论只作为历史提及，不当作现行答案。同时发布 `interface.json`，让别的插件可以按带版本的契约调用检索。

用户：
- **你本人**：接需求、遇到问题时先查一下。
- **其他插件**（以后的 spec-guard 探测）：读 `interface.json`，调用检索命令拿到结构化结果。

## 要你确认的假设

1. **拆成两层**：
   - **检索层**是脚本 `kb.py ask search <词> [<词> …] [--json]`：确定性的、只读的。它负责在 index 和 wiki 全文里匹配多个词（任意一个命中即可，不区分大小写），给出候选页面和命中的行；
   - **回答层**是 skill `/kb:ask`：由模型抽取关键词并扩展同义词和中英文术语，调用检索，读候选页面全文，然后综合回答。
   
   别的插件只依赖检索层的 JSON 契约，不依赖模型怎么回答。
2. **每条命中都标出"所在区域"**：`current`（正文）、`outdated`（`[!outdated]` 块内）、`disputed`（`[!disputed]` 块内）。页面 `status: superseded` 时，整页的命中都标为 `outdated`，同时给出 `superseded_by`。这样"过时结论不当作现行答案"靠格式就能判断，不需要模型去理解文字。
3. **排序简单透明**：按"命中了几个不同的词"排，标题和 index 里的命中加权；只有 `outdated` 区域命中的页面排在后面。不做向量检索（PRD 规定的阈值是 300 页、index 40KB，在那之前不引入）。默认最多返回 10 页，可以用 `--limit` 调。
4. **回答的规矩**（写进 SKILL.md）：
   - 每个结论都附上页面链接；需要时也附 inbox 原文的链接；
   - 结论只能来自页面里 `current` 区域的内容；`outdated` 的只能作为"曾经认为……，后被 YYYY-MM-DD 的经验推翻"来提；`disputed` 的要把各方说法都摆出来；
   - 知识库里没有的，明说"知识库里没有"，并列出搜过的词；不要用模型自己的知识冒充知识库的内容。如果要补充模型自己的知识，必须明确分开标注；
   - **不写任何文件**。把回答归档成新页面是 Phase 5 的事。
5. **`interface.json` 放在插件根目录**，格式参照本机 agent-relay 的先例，至少包含契约版本、检索命令的参数模板、JSON 输出的 schema 版本、skill 名。契约说明写在 `references/interface.md` 里。契约版本从 `1.0` 开始；以后改动输出结构时必须升级版本号（PRD 6.5）。
6. **跨项目就是靠 plugin-shell 的配置定位**：在任何目录下，ask 都查 `~/.config/kb/config.json` 里配置的那个知识库，不需要额外的机制。

## 检索输出契约（`ask search --json`，schema 1）

```json
{
  "schema": 1,
  "ok": true,
  "vault": "/绝对路径",
  "terms": ["缓存", "cache"],
  "pages": [
    {
      "path": "wiki/pitfalls/codex-plugin-cache-refresh.md",
      "title": "Codex 插件改了 skill 不生效：读的是缓存副本",
      "type": "pitfall",
      "status": "current",
      "superseded_by": null,
      "updated": "2026-11-19",
      "raw": ["inbox/2026-11-19-codex-plugin-cache-refresh.md"],
      "score": 7,
      "matched_terms": ["缓存", "cache"],
      "hits": [{"line": 18, "zone": "current", "text": "……命中行，截断到 200 字……"}]
    }
  ],
  "truncated": false
}
```

退出码：0 有命中，1 没有命中（仍然输出合法 JSON，`pages` 为空），2 配置或用法错误。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py ask search 缓存 cache 插件 --json
python3 -B plugins/kb/scripts/kb.py ask search 缓存 cache --limit 5
```

## Project Structure（本模块新增或修改）

```
plugins/kb/
├── interface.json              # 新增：契约 1.0
├── references/interface.md     # 新增：契约说明
├── skills/ask/SKILL.md         # 新增（主会话写）
├── scripts/kblib/ask.py        # 新增：检索、区域标注、排序
└── scripts/kb.py               # 修改：ask search 子命令
tests/test_ask.py
scripts/check-manifests.py      # 修改：同时校验 interface.json（存在、能解析、契约版本格式正确、引用的 skill 存在）
README.md                       # 修改
```

## Testing Strategy

- 区域标注：`current`、`[!outdated]`、`[!disputed]`、`status: superseded` 的整页，各有用例；代码块里的命中归入它所在的区域。
- 排序：标题命中优先；只有 outdated 区域命中的页面排在后面；`--limit` 生效，`truncated` 正确。
- 多词任意命中、不区分大小写、中英文混排。
- 没有命中时退出 1，JSON 仍然合法。
- 契约：输出对照一份 schema 断言字段和类型；`check-manifests.py` 校验 interface.json。
- 用 dispatch 样例：搜"派活""成本"，旧结论的命中标为 `outdated`，"现行判据"一节的命中标为 `current`。
- 只读：搜索前后知识库的文件和 git 状态都不变。

## Boundaries

- **总是**：只读；回答必须附出处；过时结论不当作现行答案。
- **先问**：无（ask 不写任何东西）。
- **不做**：归档回答（Phase 5）；向量检索；改别的插件（spec-guard 接入走总负责人）；用模型自己的知识冒充知识库内容。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖 Testing Strategy 的每一项。
- **AC2** `ask search --json` 的输出符合上面的契约（schema 1），没有命中时退出 1 且 JSON 合法。
- **AC3** `interface.json` 和 `references/interface.md` 发布了契约 1.0；`check-manifests.py` 会校验它。
- **AC4** SKILL.md 写清：抽词（含同义词、中英文）→ 检索 → 读候选全文 → 只基于 current 区域回答并附链接 → outdated 作为历史提及 → 没找到就明说并列出搜过的词 → 不写文件。
- **AC5（真实环境，MVP 验收第 3 条）** 在**另一个项目**（tab-leader）里用 `claude -p` 新开进程问"Codex 里改了插件的 skill 为什么不生效？"，回答要命中 save 模块写入的那一页并附上链接。
- **AC6（过时结论）** 用 dispatch 样例（通过 `KB_CONFIG` 指向一个临时副本）在 `claude -p` 里问"把机械活派给子代理省钱吗？"，回答的结论必须是"默认不派，看能否减少主会话轮次"，旧结论只能作为被推翻的历史提及。
- **AC7（跨宿主）** 通过 delegate **只读**派 Codex 在 tab-leader 问同一个问题（ask 不写文件，只读沙箱就够），回答命中同一页并附出处。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/references/interface.md` | 新建：契约说明 |
| `plugins/kb/skills/ask/SKILL.md` | 新建 |
| `README.md` | 修改：`/kb:ask` 标为已实现，补检索命令和契约说明 |

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
