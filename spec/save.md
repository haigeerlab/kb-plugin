<!-- spec-guard: review approved f6d89132a55e -->

# Spec: save

## Objective

能力图第 4 个模块，MVP 的核心。目标是解决完一个问题后，用一句 `/kb:save`（或者直接说"存进 kb"）把经验沉淀下来：

1. AI 从当前会话里提炼经验，写成一条 inbox 条目（原文）；
2. 当场编译：决定是新建页面、并入已有页面、标记冲突，还是"没有新内容"；
3. 脚本做脱敏、契约校验，生成改动预览；
4. 你看一眼预览，确认一次；
5. 写入知识库，并做一次本地 commit。

这是第一个调用模型的模块。原则延续前面：**判断交给模型，正确性交给脚本**。模型负责提炼、分类、写作；脚本保证格式、出处、脱敏、只追加、原子写入。

用户：你本人，在任何项目的 Claude Code 或 Codex 会话里使用。

## 要你确认的假设

1. **模型不直接改知识库文件。** 模型把要写的内容放进一个**草稿目录**（系统临时目录下 `kb-save-<时间戳>/`，目录结构镜像知识库的相对路径），然后调用脚本：
   - `kb.py save preview <草稿目录>`：脚本把草稿叠加到知识库的一份临时副本上，依次做路径白名单、脱敏（先替换代号）、`kb check` 全量校验，然后输出改动预览（新建文件列表 + 修改文件的 diff）和一个**预览指纹**；
   - `kb.py save apply <草稿目录> --confirm <指纹>`：再校验一遍，确认知识库从预览到现在没有变化（指纹覆盖知识库 HEAD、工作区状态、草稿内容），然后写入并 `git commit`。
   
   这样，"没过校验的内容进入知识库"在结构上就不可能发生，而模型只需要写文件、跑两条命令。这是 claude-obsidian 事务机制的轻量版：不需要手写 bundle，也不需要手算哈希。
2. **草稿目录里允许出现的路径**：
   - `inbox/` 下的**新文件**，有且只有 1 个；
   - `wiki/` 下的新文件或修改；
   - `index.md`、`log.md`。
   
   其他路径、删除文件、修改已有的 inbox 或 raw 文件，一律拒绝。
3. **inbox 条目是模型整理过的会话摘录，不是会话全文。** 它要包含后面页面会引用的全部"承重事实"：命令、版本号、报错原文、数字。这些都要从会话里逐字摘出来，因为出处校验要求页面上的这些事实必须在 inbox 里逐字存在。frontmatter 的 `source` 写 `session`，`host` 写当前宿主。
4. **编译时的处置照搬 karpathy 的四种，加上一条约束**：
   - **新建**：没有同主题的页面；
   - **并入**：有同一核心结论的页面，在原页面上更新，追加 `raw`，刷新 `updated`；
   - **冲突**：新经验推翻了旧结论，旧结论整段移进 `[!outdated]` 块，新结论写成现行内容；说不清谁对时写进 `[!disputed]` 块；
   - **没有新内容**：只写 inbox 和 log，不改 wiki。
   - **约束**：判断前必须先读 index，再用关键词、同义词和中英文术语全文搜索 `wiki/`；在两处都没找到时，才能判"新建"。
5. **一次 save 只处理一条经验**，可以同时改多个页面（比如主页面加上项目枢纽页）。会话里有多条经验时，模型先列出来让你挑，或者你分几次 save。
6. **确认只有一次**：预览给出后，你回复"确认"之类的明确同意，模型就执行 apply。预览里如果有你不满意的地方，你直接说，模型改草稿后重新 preview。
7. **本地 commit 自动做，不 push**（PRD 开放问题 2，已批准）。提交信息是 `save: <标题>`，log.md 里同步记一条 `## [日期] save | <标题>`。
8. **两个宿主共用同一个 skill**：`/kb:save` 的 SKILL.md 写明完整流程，Claude Code 和 Codex 都按它执行。
9. **SKILL.md 由主会话写，脚本由 Codex 实现。** SKILL.md 本身就是"判断交给模型"的那一半，是写作和取舍，不是机械实现。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py save preview <草稿目录> [--json]
python3 -B plugins/kb/scripts/kb.py save apply <草稿目录> --confirm <指纹> [--json]
```

退出码：0 成功；1 校验或脱敏没通过（输出所有问题，不写入）；2 用法或配置错误；3 指纹不匹配（知识库或草稿在预览后发生了变化，需要重新 preview）。

`preview --json`：`{ok, fingerprint, created: [...], modified: [...], diff: "...", replaced_aliases: N, findings: [...]}`。

## Project Structure（本模块新增或修改）

```
plugins/kb/
├── skills/save/SKILL.md          # 新增（主会话写）：提炼 → 草稿 → preview → 确认 → apply
├── scripts/kblib/save.py         # 新增：草稿校验、叠加副本、指纹、原子写入、git commit
└── scripts/kb.py                 # 修改：save 子命令
tests/test_save.py
README.md                         # 修改：/kb:save 标为已实现
```

## Code Style

延续前几个模块。写入要原子：先把所有文件写到知识库内的临时文件，再逐个 `os.replace`；任何一步失败就回滚已经写入的文件，然后报错。git commit 失败时，写入的文件保持原样，并报告失败原因（不自动 reset）。

## Testing Strategy

- `preview`：合法草稿能通过；违反路径白名单（改已有 inbox、写 `raw/`、写知识库外、删除文件、2 个 inbox 文件）分别报错；草稿含假密钥时报 `redaction`；草稿让 `kb check` 失败（比如没进 index）时报对应检查码；代号替换体现在 diff 里。
- 指纹：preview 之后再改草稿、往知识库里提交新内容、修改知识库工作区，apply 都返回 3，并且不写入。
- `apply`：写入后 `kb check` 为 0 问题、git log 多 1 个提交、提交信息正确；模拟中途写入失败时完整回滚。
- 端到端：在临时知识库里用三段素材依次 save 三次（新建坑页 → 新建决策页 → 用推翻性证据更新决策页，生成 `[!outdated]` 块），每次都 0 问题，git 历史 3 个提交，inbox 3 个文件都没被改过。
- SKILL.md：通过根目录解析片段一致性测试。

## Boundaries

- **总是**：先 preview 再 apply；apply 必须带 preview 给出的指纹；只写知识库；写入前脱敏。
- **先问**：每次 apply（就是那一次确认）；会话里有多条经验时，问存哪条。
- **不做**：push；删除或改写 inbox 和 raw；联网；把会话全文存进去；跨多条经验的批量 save（那是 inbox-compile）；语义层面的去重和矛盾检测（lint-semantic）。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖 Testing Strategy 的每一项。
- **AC2** 路径白名单、脱敏、契约校验，任何一项没通过时 apply 都不写入；指纹不匹配时返回 3，不写入。
- **AC3** 端到端三次 save（含一次"冲突"处置）全部 0 问题，git 历史和 inbox 的不可改性都符合预期。
- **AC4** `/kb:save` 的 SKILL.md 写清：确定范围（多条经验时让用户挑）→ 提炼 inbox 条目（承重事实逐字摘录）→ 先读 index 再全文检索（含同义词）→ 选处置 → 按模板写页面、更新 index 和 log → preview → 把预览原样给用户 → 用户明确确认后 apply → 报告提交号和改动文件。处置规则、标注块写法、敏感内容禁写项都要写进去或者引用 SCHEMA。
- **AC5（gate，真实环境）** 在**本会话**里用 `/kb:save` 沉淀一条今天的真实经验："Codex 安装的是插件缓存副本，改了 skill 要重新 `codex plugin add` 才能刷新；`marketplace upgrade` 对本地目录市场无效"。这条要进你真实的知识库，你在预览时确认一次，然后 `kb check` 0 问题，知识库多 1 个提交。
- **AC6（gate，跨宿主）** 通过 delegate 派 Codex 在另一个项目目录里执行一次 save 的 **preview**（不 apply），确认 Codex 能走通流程，并能找到 AC5 那条经验已经存在、把处置判为"并入"或"没有新内容"。
- **AC7** README 把 `/kb:save` 标为已实现，写明一次 save 的流程和退出码。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/skills/save/SKILL.md` | 新建 |
| `README.md` | 修改 |

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
- 2026-11-19（lint 模块 T2）：SKILL.md 第 6 步补充——处置为"没有新内容"时，log 条目正文必须写出本次 inbox 路径，供 lint 区分已处理的 inbox 和积压。只改 SKILL.md 文字，脚本行为不变。
