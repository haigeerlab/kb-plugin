---
name: lint
description: 用户要给 kb 知识库做体检时使用，例如“/kb:lint”“检查一下知识库”“kb 有没有断链或过期的内容”，或者批量 save 之后想确认知识库是否健康。输出确定性的体检报告；只有断链、index 不一致这几类有唯一正确改法的问题，才在用户确认后做安全修复。
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

## 5. 自动修复范围以外的问题

只给建议，不动手。需要改页面内容的，建议用户用 `/kb:save` 走一次"并入"或"冲突"处置；需要放行脱敏误报的，告诉用户可以在知识库根目录的 `redaction-allow.txt` 中添加记录，由用户自己决定。
