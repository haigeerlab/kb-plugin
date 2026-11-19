<!-- spec-guard: review approved fb94e3e945cb -->

# Spec: lint-semantic

## Objective

能力图第 10 个模块，也是集成阶段最后一个。对应 PRD 场景 S3 的语义部分：在确定性体检之外，找出四类**只有读懂内容才能发现**的问题：

1. **疑似矛盾**：两页的现行结论互相冲突，却都没有标 `[!disputed]` 或 `[!outdated]`；
2. **疑似过期**：结论绑定了具体版本、日期或"目前""最新"这类时效词，而页面很久没核实；
3. **缺页概念**：一个概念在多页反复出现，却没有自己的页面（通常该补一张 tech 或 pattern 页）；
4. **建议升级为规则**：高频、已验证、可以写成"总是 / 永远不要"的条目，适合将来用 `/kb promote`（Phase 6）写进 CLAUDE.md、AGENTS.md 或 skill。

用户：你本人，偶尔跑一次（比如每月，或者批量 compile 之后）。产出是一份报告，**不改知识库**。

## 要你确认的假设

1. **形态：并入 `/kb:lint`，作为可选的第二段，不新增命令。** 默认的 `/kb:lint` 照旧只跑确定性检查（便宜、可重复）；你说"深度体检""语义检查""查矛盾"之类的话时，lint SKILL 在确定性报告之后再跑语义段。理由：少一个命令就少一个要记的入口；语义段要花模型 token，不该每次都跑。
2. **分工：脚本圈候选、模型判断、脚本核对引文。** 这延续 constraint = quality：
   - **`kb.py lint semantic-pack`（脚本，确定性）**：只读知识库，输出一个紧凑的 JSON 包，供模型阅读。内容包括：每页的标题、类型、标签、created/updated、`## 相关`链接，以及**标注块以外的现行结论正文**（按页截断）；再加上四类候选线索——
     - 矛盾：标签或关键术语有交集、彼此没有标注块指向的页面对，最多 30 对；
     - 过期：含版本号（如 `0.166.0`、`v5`）、具体年月或"目前 / 最新 / 现在 / currently / latest"的现行句子，附页面 updated 距今天数；
     - 缺页：在 2 页及以上出现、却不是任何页面标题或 slug 的标签和反引号术语；
     - 升级：被 2 页及以上链接、或在 log 里被 save/compile 更新过 2 次及以上、或正文含"总是 / 必须 / 永远不要 / 不要"祈使句的 pitfall 和 decision 页。
     
     脚本只出线索，不下结论。
   - **模型（lint SKILL 里）**：只读这个包（必要时再读个别页面全文），判断哪些线索是真问题，写成 findings JSON：类别、涉及页面、**逐字引文**、理由、建议动作。
   - **`kb.py lint semantic-verify <findings.json>`（脚本，确定性）**：逐条核对 findings 里的引文是否**逐字存在于所引页面的现行结论区**（复用 evidence 模块的逐字比对），页面路径是否存在。核对不通过的条目不进报告正文，单列为"引文核对失败，已剔除"。最后按四类输出报告，并且先过一遍打码。
   
   这样模型能决定"是不是问题"，但不能编造证据：报告里每条疑似问题都能回到原文。
3. **只出报告，不改知识库，也不写 log。** 每类问题给出建议动作，由你决定要不要做、怎么做：
   - 矛盾 → 用 `/kb:save` 把其中一方并入另一方，或给旧结论加 `[!outdated]`、给双方加 `[!disputed]`；
   - 过期 → 重新核实后更新 updated，或者加 `[!outdated]`；
   - 缺页 → 写一张新页（`/kb:save` 或手写），并和相关页互链；
   - 升级 → 记下来，等 Phase 6 的 `/kb promote`。
   
   本模块不做"一键修复"，因为语义问题没有唯一正确的改法（这和确定性 lint 的"安全修复"不同）。
4. **核实过期只在本机、只读、可选。** 遇到"某工具 X 版本"类的过期线索时，模型**可以**跑这个工具本机的只读版本命令（如 `codex --version`、`npm view <pkg> version`）来比对，并在报告里写出命令和结果；不联网就无法核实的，只标"需要核实"，不猜。是否跑命令由 SKILL 列出的白名单决定：`--version`、`-V`、`npm view <pkg> version`，以及读取本地 `node_modules/<pkg>/package.json`。
5. **规模与成本上限。** pack 的大小上限是 60KB（超出时按 updated 从旧到新优先保留、截断正文并在包里注明）；矛盾候选最多 30 对。现在知识库只有 6 页，远低于上限；上限是给以后用的。PRD 定的引入检索工具的阈值（300 页、index 40KB）不变。
6. **两个宿主都能用。** pack 和 verify 只读知识库，Codex 只读沙箱也能跑；findings JSON 写在临时目录（Codex 只读沙箱写不了时，SKILL 让模型把 JSON 直接通过 stdin 交给 verify：`semantic-verify -`）。
7. **不做的事**：不自动合并或标注页面；不调用 promote；不联网核实；不读会话记录和 delegate 快照（那是 compile 的输入，不是知识库内容）。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py lint semantic-pack [--json]            # 默认就输出 JSON
python3 -B plugins/kb/scripts/kb.py lint semantic-verify <findings.json|-> [--json]
```

findings JSON（模型产出，verify 消费）：

```json
{"version": 1, "findings": [
  {"category": "contradiction|stale|missing-page|promote",
   "pages": ["wiki/pitfalls/a.md", "wiki/decisions/b.md"],
   "quotes": [{"page": "wiki/pitfalls/a.md", "text": "逐字引文"}],
   "reason": "为什么这是问题",
   "action": "建议动作",
   "verified_by": "可选：本机只读核实命令与结果"}
]}
```

## Project Structure（本模块新增或修改）

```
plugins/kb/scripts/kblib/semantic.py        # 新增：pack（候选线索）与 verify（引文逐字核对、报告）
plugins/kb/scripts/kb.py                    # 修改：lint semantic-pack / semantic-verify
plugins/kb/skills/lint/SKILL.md             # 修改（主会话）：可选的语义段、判断标准、只读核实白名单
tests/test_semantic.py
tests/fixtures/vaults/semantic/             # 新增：埋好四类问题的样例知识库，外加干扰项
README.md
```

## Testing Strategy

- **pack**：用埋了四类问题的样例知识库，断言每一类埋点都出现在对应的候选线索里；干扰项（标注块里的旧结论、已经标了 disputed 的一对、已有页面的概念）不出现；标注块内的文字不进入现行结论正文；60KB 上限和 30 对上限生效；pack 前后知识库文件哈希不变。
- **verify**：逐字存在的引文保留；改一个字、引自标注块、引自不存在的页面、页面路径越界（`../`）的条目都被剔除并单列；未知 category、缺字段、坏 JSON 时报错退出且不崩溃；stdin 输入可用；报告经过打码（假密钥运行时拼接）。
- **回归**：确定性 lint 的原有测试保持全绿；不带语义段时 `/kb:lint` 行为不变。
- 模型判断这一段无法单元测试，放进真实验证（AC5、AC6）。

## Boundaries

- **总是**：只读知识库；报告里的每条疑似问题都要有通过逐字核对的引文。
- **先问**：任何对知识库的改动（走 `/kb:save` 或手改，照常预览确认）。
- **不做**：自动修改、写 log、联网、调用 promote、读会话记录或 delegate 快照。

## Success Criteria

- **AC1** 单元测试全部通过；确定性 lint 的原有测试保持全绿。
- **AC2** pack 对样例知识库：四类埋点全部进入候选线索，干扰项都不进；两个上限生效；只读。
- **AC3** verify：逐字引文才能进报告，伪造、篡改、越界、引自标注块的引文全部剔除并单列；报告打码。
- **AC4** lint SKILL 写明：什么时候跑语义段、四类问题的判断标准（尤其是"不算矛盾"的情形，例如适用版本或场景不同）、只读核实白名单、findings JSON 格式、"只出报告不改库"。
- **AC5（样例真实运行）** 在本会话里对样例知识库走一遍 `/kb:lint` 语义段：四类埋点至少各命中一条，干扰项没有被报成问题；如果模型编了一条引文，verify 会把它剔除。
- **AC6（真实知识库）** 对你现有的知识库跑一次语义段，报告给你看；你判断每条是否有用。知识库在运行前后没有任何改动（`git status` 干净、HEAD 不变）。
- **AC7** README 写清语义体检的用法、四类问题、"只出报告"。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `README.md` | `/kb:lint` 一节加"语义体检（可选）" |
| `plugins/kb/skills/lint/SKILL.md` | 增加可选的语义段 |
| `spec/lint.md` | 加一行变更记录（lint 增加可选的语义段，确定性部分不变） |

## Open Questions

无。

## 变更记录

- 2026-11-20 初稿。
