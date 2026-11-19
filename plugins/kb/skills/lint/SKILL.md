---
name: lint
description: 用户要给 kb 知识库做体检时使用，例如“/kb:lint”“检查一下知识库”“kb 有没有断链或过期的内容”，或者批量 save 之后想确认知识库是否健康。输出确定性的体检报告；只有断链、index 不一致这几类有唯一正确改法的问题，才在用户确认后做安全修复。用户说“深度体检”“语义检查”“查一下有没有矛盾”“哪些可以升级成规则”时，再加跑可选的语义体检，只出报告。
---

# 给 kb 知识库做体检

**三条硬约束，先于一切步骤：**

1. **报告不写进知识库。** 只在回复里呈现。
2. **只有 `lint fix` 能改知识库，而且要在用户本轮明确同意之后才能执行 apply。** 不手动编辑知识库里的任何文件。
3. **把事实和建议分开写。** 报告里的问题是事实；你提出的处理办法是建议，要明确标注。孤儿页、疑似过期这类提示不一定是问题，不要推断用户的意图。

## 1. 定位插件

在 bash 中执行下面的插件根目录解析片段；失败就停下，原样转述原因。

```bash
ROOT="${CLAUDE_PLUGIN_ROOT}"
[ -n "$ROOT" ] || ROOT="${PLUGIN_ROOT:-}"
WHY="宿主没有把插件根目录代入命令，环境里也没有 CLAUDE_PLUGIN_ROOT 或 PLUGIN_ROOT"
if [ -z "$ROOT" ]; then
  if ! command -v codex >/dev/null 2>&1; then
    WHY="${WHY}；也没有 codex 可查询"
  else
    LIST="$(codex plugin list --available --json 2>/dev/null)"; RC=$?
    ROOT="$(printf '%s' "$LIST" | python3 -c '
import json, sys
try:
    plugins = json.load(sys.stdin).get("installed", [])
except (AttributeError, TypeError, ValueError):
    sys.exit(3)
for plugin in plugins:
    if isinstance(plugin, dict) and plugin.get("name") == "kb" and plugin.get("installed") and plugin.get("enabled"):
        source = plugin.get("source")
        path = source.get("path") if isinstance(source, dict) else None
        if isinstance(path, str) and path:
            print(path)
            sys.exit(0)
sys.exit(4)
')"
    case $? in
      0) ;;
      4) WHY="${WHY}；codex plugin list 没有列出已启用且带路径的 kb" ;;
      *) WHY="${WHY}；codex plugin list 查询失败（退出码 ${RC}）或输出无法解析" ;;
    esac
  fi
fi
[ -n "$ROOT" ] || { echo "kb 无法定位插件根目录：${WHY}。这是定位失败，不代表插件未安装。" >&2; exit 2; }
[ -d "$ROOT" ] || { echo "kb 插件根目录不存在：${ROOT}（插件可能刚更新或被移除，重开会话后再试）。" >&2; exit 2; }
```

## 2. 运行体检

在同一个 shell 里：

```bash
python3 -B "$ROOT/scripts/kb.py" lint
```

用户指定了过期天数时加 `--stale-days N`。退出码 0 表示没有 check 级问题（可能还有提示），1 表示有 check 级问题，2 表示配置或用法错误：原样转述错误后停下。

## 3. 解释报告

按报告的分组顺序呈现，保留脚本给出的路径、行号和数量：

1. **导航断裂**（断链、index）：会让 ask 找不到页面或链接打不开，优先处理。
2. **内容可信度**（出处不符、原文被改、敏感内容等）：逐条说明是哪一处、为什么不可信。`redaction` 命中不要回显原文。
3. **格式**：说明不符合 SCHEMA 的哪一条。
4. **维护提示**（孤儿页、疑似过期、inbox 积压）：只是提示。比如孤儿页可能只是还没有相关页面可以链接，不要把它说成错误。
5. **规模指标**：对照阈值说明离引入检索工具还有多远；"暂无数据"照原样说明，不要估算。

每组之后，用"**建议：**"另起一段，写你的处理建议。

## 4. 安全修复（有可修复项时）

```bash
python3 -B "$ROOT/scripts/kb.py" lint fix preview
```

- 退出码 0 且说明"无需修复"：告诉用户没有可以自动修复的问题。
- 有可修复项：在回复正文里**原样贴出完整的 diff 和预览指纹**，说明会修哪几处、哪些问题不在自动修复范围内，然后问用户是否执行。

用户在本轮明确同意后：

```bash
python3 -B "$ROOT/scripts/kb.py" lint fix apply --confirm <指纹>
```

- 退出码 3：知识库在预览之后发生了变化，回到本步重新预览，再请用户确认。
- 成功：报告提交号，并重新运行第 2 步，确认已修复的问题不再出现。
- 报"文件已写入但提交失败；已记录待提交"：把报错里给出的 `commit-pending` 命令**原样**告诉用户，请用户在 Claude Code、终端，或者在交互式 Codex 里申请提权后运行。**不要自己执行 `git add`、`git commit`，也不要去改 `.git` 或 `.kb-pending.json`。**
- 报"有待提交记录"：先请用户运行 `commit-pending`，完成后再从第 2 步开始。

## 5. 自动修复范围以外的问题

只给建议，不动手。需要改页面内容的，建议用户用 `/kb:save` 走一次"并入"或"冲突"处置；需要放行脱敏误报的，告诉用户可以在知识库根目录的 `redaction-allow.txt` 中添加记录，由用户自己决定。

## 6. 语义体检（可选）

**只在用户明确要求时跑**（"深度体检""语义检查""查矛盾""哪些能升级成规则"之类）。它要花模型 token，不属于默认的 `/kb:lint`。先跑完第 2 步的确定性体检；有 check 级问题时，先报告这些问题，并问用户是否仍要继续语义段。

语义段**只出报告**：不改知识库任何文件、不写 log、不联网、不调用 promote。

### 6.1 取候选包

```bash
python3 -B "$ROOT/scripts/kb.py" lint semantic-pack
```

输出是 JSON：每页的现行结论正文（标注块已去掉）和四类候选线索。线索只是事实，不是结论。包里写了 `truncated` 时，告诉用户有哪些页面被截断。只有在判断某条线索需要上下文时，才去读那一页全文。

### 6.2 判断

对每条线索判断是不是真问题。**宁可少报，不要误报**：

| 类别 | 算问题 | 不算问题 |
|---|---|---|
| 疑似矛盾 contradiction | 两页的现行结论对同一件事给出互斥的说法，且都没有标注 | 适用版本、平台或场景不同，且页面已经写明；一方已经用 `[!outdated]` 或 `[!disputed]` 处理过；只是侧重点不同 |
| 疑似过期 stale | 现行结论绑定了具体版本或"目前 / 最新"，而页面很久没更新，或者本机可查到的版本已经不同 | 版本号只是记录"在哪个版本上验证过"，且页面不久前更新过；句子在标注块里 |
| 缺页概念 missing-page | 一个工具、机制或概念在多页反复出现，读者需要一张页面来理解它 | 已有页面（标题不同但讲的是它）；只是一个命令或参数；只在一页里出现 |
| 建议升级 promote | 已验证、可以写成"总是 / 永远不要"、违反会出事，且有多次出现或多页引用的佐证 | 只有一句祈使句、没有其他佐证；依赖具体场景，写成规则会误伤 |

**可选的本机只读核实**（仅限疑似过期）：白名单只有 `<工具> --version`、`<工具> -V`、`npm view <包名> version`、读取本地 `node_modules/<包名>/package.json`。跑了的，把命令和输出写进该条的 `verified_by`；不在白名单里、或需要联网才能确认的，只写"需要核实"，不要猜。

### 6.3 写 findings 并核对引文

把判断结果写成 JSON（格式见下）。每条至少一处 `quotes`，**引文必须从包里的现行结论正文逐字复制**，不要改写，也不要引标注块里的文字：

```json
{"version": 1, "findings": [
  {"category": "contradiction",
   "pages": ["wiki/pitfalls/a.md", "wiki/decisions/b.md"],
   "quotes": [{"page": "wiki/pitfalls/a.md", "text": "逐字引文"},
              {"page": "wiki/decisions/b.md", "text": "逐字引文"}],
   "reason": "为什么这是问题",
   "action": "建议动作",
   "verified_by": ""}
]}
```

`category` 只能是 `contradiction`、`stale`、`missing-page`、`promote`。写进临时文件后核对：

```bash
F="$(mktemp "${TMPDIR:-/tmp}/kb-semantic-XXXXXX")"
# 把 findings JSON 写入 "$F"
python3 -B "$ROOT/scripts/kb.py" lint semantic-verify "$F"
```

在 Codex 只读沙箱里写不了临时文件时，改用 stdin：`printf '%s' '<findings JSON>' | python3 -B "$ROOT/scripts/kb.py" lint semantic-verify -`。

### 6.4 报告

按 verify 的输出呈现：四类各一节，每条写清涉及的页面、引文、理由和**建议动作**：

- 矛盾：用 `/kb:save` 把其中一方并入另一方，或者给旧结论加 `[!outdated]`、给双方加 `[!disputed]`；
- 过期：重新核实后更新页面和 updated，或者加 `[!outdated]`；
- 缺页：写一张新页（`/kb:save`），并和相关页互链；
- 升级：记下来，等 `/kb promote`（Phase 6）。

"引文核对失败，已剔除"的条目**原样列出并说明已剔除**，不要当作结论。哪一类都没有发现时，直接说明"没有发现"，这也是有效结论。最后删除临时文件（确认变量非空、路径在临时目录下）。不要动手修改，等用户决定。
