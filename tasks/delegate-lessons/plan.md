<!-- spec-guard: review approved -->

# Plan: delegate-lessons

> Spec：[spec/delegate-lessons.md](../../spec/delegate-lessons.md)（已批准）

## 执行方式

和 inbox-compile 一样：fixture 由主会话构造（只取真实结果文件的结构，内容虚构），实现派给 Codex，compile SKILL 由主会话修改，真实环境验证作为 gate。

## 任务

### T0 delegate 结果 fixture（主会话）
- 参照本机一份真实结果文件的**字段结构**，在 `tests/fixtures/delegate/` 下构造约 8 组 `result.json` 和 `answer` 文件，覆盖：
  - done 且答复较长；
  - done 且答复很短、命令全部成功（应跳过）；
  - done 且答复很短、但有失败命令（应收集）；
  - review（应跳过）；
  - needs-input 的链头加上同一链的 done（只收后者）；
  - failed、timeout；
  - schema 不是 1；
  - 损坏的 JSON；
  - 答复文件缺失。
- 内容全部虚构，不含假密钥（假密钥由测试在运行时拼接）。另写一份 README 说明每组的用途。
- 检查点：report

### T1 实现（派 Codex，--write，期限 1800 秒，后台）
- 内容：
  - `delegate_lessons.py`：扫描、过滤、按链去重、增量处理、取快照、入队；
  - `candidates.py`：增加 `source` 字段，list 和 show 支持 delegate 候选；
  - `capture.py`：在 hook 里顺带调用扫描（受时限和数量上限约束，异常一律吞掉）；
  - `config.py`：新增两个配置字段；
  - `kb.py candidates scan-delegate`；
  - `tests/test_delegate_lessons.py`；
  - README 补充说明。
- 约束：只读 `KB_DELEGATE_DIR`；不碰 `skills/`；session-capture、candidates、compile 的原有测试不改且全绿；不碰真实的知识库、配置、状态目录和真实的 delegate 目录；不联网；不提交。
- 检查点：report

### T2 compile SKILL 和 inbox-compile 的变更记录（主会话，与 T1 并行）
- compile SKILL 第 2 步：说明 delegate 候选怎么读（答复里的发现、原因、解法，以及失败的命令），给出"没有可复用经验就建议丢弃"的标准，并说明编译时新建 inbox 要写 `source: delegate`、`host: codex`。
- `spec/inbox-compile.md` 加一行变更记录。
- 检查点：report

### T3 主会话复核与对抗抽查
- 逐条核验 AC1–AC5、AC7。对抗抽查：
  1. 扫描前后，对 fixture 目录里每个文件算哈希，必须全部不变（只读）；
  2. 再扫描一次，不新增候选（增量）；
  3. 放 25 个新结果，第一次只处理 20 个，第二次处理剩下的 5 个；
  4. 用 hooks.json 的原始命令执行 hook，`KB_DELEGATE_DIR` 指向一个有 200 个文件的目录：退出 0、无输出、耗时小于 1 秒；
  5. 在某个答复里放一个运行时拼接的假密钥，`candidates show` 的输出里必须是打码后的；
  6. `git diff` 确认原有测试文件没有改动。
- 通读 `delegate_lessons.py`；通过后提交，刷新 Codex 缓存。
- 检查点：report

### T4 真实环境验证（gate，模块最终验收）
- 停下来问你后执行：
  1. 对本机真实的 delegate 目录跑一次 `scan-delegate`，报告收集和跳过的数量和理由（只显示 runId、仓库名、状态和理由，不显示答复内容）；
  2. 在本会话里走 `/kb:compile` 的清单步骤：你看到 delegate 候选后，挑一条编译，或者全部丢弃；
  3. 如果选了编译，就走完预览、确认、写入，`kb check` 为 0 问题；
  4. delegate 目录里文件的哈希在扫描前后不变。
- 检查点：gate

## 风险

| 风险 | 应对 |
|---|---|
| hook 已经启用，Codex 改 capture.py 时会在复核之前生效 | hook 的 bash 外层是 `>/dev/null 2>&1; exit 0`，Python 出错最坏也只是静默不做事，不影响会话退出；T3 抽查 4 用原始命令验证 |
| delegate 目录被系统清理，或 delegate 升级后格式变化 | 只认 schema 1，其他的跳过并记日志；字段缺失时跳过，不崩溃 |
| 答复里经验稀疏，候选质量低 | compile SKILL 给出丢弃标准；Spec 假设 5 留了后续改进的口子（提示词侧） |
| 快照里带出敏感内容 | 快照只存本机；show 时先打码；编译进 inbox 时照常经过脱敏扫描 |

## 变更记录

- 2026-11-19 初稿。
