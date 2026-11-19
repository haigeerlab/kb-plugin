# Todo: inbox-compile

- [x] T0 会话记录 fixture，主会话（report）— `783ca74`；按真实结构构造、内容虚构，覆盖 8 类记录和损坏行，每类该跳过的内容都带 `*-MARKER`
- [x] T1 实现，派 Codex --write（report）— run `20261119182917.83257`，status=done，`--check` 通过；Git 验收块：基线 `783ca74`，新增 candidates.py、compile.py、两个测试文件，修改 kb.py、README、lint.py（把积压判定抽成共享的 `inbox_backlog`）、save.py（草稿读取加 `operation` 参数，compile 允许 0 或 1 个 inbox）、writer.py（待提交记录允许 compile，1 行）；旧测试和 fixture 都没有改动
- [x] T2 compile SKILL.md，主会话（report）— 127 行，四条硬约束放在最前；同一批多项会共同修改 index 和 log，所以第二项起在前一项写入之后重新生成 index 和 log 并重新 preview；页面内容和已确认版本不一致时，停下来重新确认
- [x] T3 主会话复核与对抗抽查，并提交（report）
  - AC1：unittest 共 233 项全部通过（新增 30 项）
  - 抽查 1：fixture 工具输出里换入运行时拼接的假 token，`candidates show` 输出中没有该 token，也没有工具输出内容 ✓
  - 抽查 2：THINKING、SIDECHAIN、META、META2、ATTACH、REMINDER、TOOLUSE 标记都没有出现；用户输入和 assistant 正文保留 ✓
  - 抽查 3：同一个 session_id 入队两次，队列里只有 1 行 ✓
  - 抽查 4：会话文件删除后，list 把候选转为 expired 并写回 ✓
  - 抽查 5：compile 草稿 0 个新 inbox（引用已有积压）、1 个新 inbox 都通过；2 个被拒绝 ✓
  - 抽查 6：test_save、test_lint、test_commit_pending 的 diff 为 0 行 ✓
  - AC2–AC5：由测试和上面的抽查覆盖；SKILL 两次决定都要等用户明确回复
- [x] T4 真实环境验证 AC6、AC7（gate，用户 2026-11-19 批准执行）
  - AC6：列出最近 10 个真实会话（项目名、时间、第一句话前 30 字，只在对话里展示），用户选 #5 tab-leader（09dbe978…），入队为 `a0c5b61b1bcd`。通过已安装的 `kb:compile` 执行：
    - 第一步：`candidates show` 提取约 4 万字（截掉前 17601 字），清单 5 项，建议编译 2 项、丢弃 3 项；用户选择"编译 1 和 2，其余丢弃"
    - 第二步：检索 16 个词，正文无命中，两项都新建 pitfall；第 1 项 preview 指纹 `5aaeef9ca3e22e82`，两项页面和 inbox 全文、第 1 项的 index/log diff 一次性交给用户；用户确认"确认写入 1 和 2"
    - 第三步：第 1 项 apply → 知识库 `22683a6`；第 2 项按最新 index/log 重新生成（页面和 inbox 未变）→ 指纹 `54de9a216d143a22` → `7c29f75`；候选标为 compiled；草稿已删除；lint 的 check 级 0 问题，待处理项 0
  - AC7：用临时状态目录和**虚构样例会话**（不把用户会话交给 Codex），delegate 只读派单（tab-leader，effort low）：Codex 加载 `kb:compile`，按第 2 步列出清单和建议后停下，所有命令退出码都是 0，show 输出不含任何 MARKER，知识库没有改动
  - 本轮发现的问题（最终验收前修复，见"修复项"）：
    1. app 注入的消息（`<side-sessions-event>`、`<task-notification>`）结构上是 user 字符串，被当成用户输入保留了下来
    2. "跳过 N 条无法识别的记录"把已知但应跳过的记录类型也算进去了（真实会话里显示 898），统计口径会误导人
    3. bash 输出里的 HTML 实体（`&amp;`、`-&gt;`）没有还原
    4. 6 篇页面全部是孤儿页：save 和 compile 逐页处理，从来不建立页面之间的链接（这次的两篇出自同一次发版，本该互链）。这一项不属于本模块范围，记入 MVP 验收的已知缺口

## 修复项（T4 发现 1–3，主会话直接修）

- [x] 1 宿主注入消息：新增 `INJECTED_TAGS`（system-reminder、task-notification、side-sessions-event）整块去掉；`bash-input`/`bash-stdout` 保留
- [x] 2 "无法识别"口径：非 user/assistant 记录一律当元数据静默跳过；只统计结构认不出的对话记录和损坏行。原测试 `test_unknown_transcript_records_are_counted_but_known_skips_are_not` 断言的是旧口径（未知类型 `new-format` 要计入），已按新口径改写，并多加了两种元数据类型
- [x] 3 用户文本 `html.unescape`
- 新增测试 `test_host_injected_user_blocks_are_removed_and_entities_unescaped`；全量测试通过
- 真实会话复验（`a0c5b61b1bcd`，只统计不输出内容）：三种注入标签各 0、`&gt;`/`&amp;` 各 0、`<bash-input>` 13 条保留，"无法识别" 898 → 0
- 发现 4（页面之间不互链）不属于本模块范围，记入 MVP 验收的已知缺口
