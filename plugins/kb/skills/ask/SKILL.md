---
name: ask
description: 用户想查自己的 kb 知识库里有没有相关经验、坑或决策时使用，例如“/kb:ask …”“kb 里有没有关于 X 的经验”“以前踩过这个坑吗”“我们当时为什么这么定”，也适合接新需求、排查问题前先查一下。只读：检索知识库并基于命中页面回答，附出处，不写任何文件。
---

# 查 kb 知识库

**四条硬约束，先于一切步骤：**

1. **只读。** 不写任何文件，不改知识库。用户想把回答存下来，请他另外用 `/kb:save`。
2. **结论只能来自 `current` 区域。** 检索结果里标为 `outdated` 的内容，只能写成"曾经认为……，后被 YYYY-MM-DD 的经验推翻"；标为 `disputed` 的，要把各方说法都摆出来，不替用户选边。
3. **每个结论都附出处**：页面链接，必要时加上 inbox 原文链接。
4. **知识库里没有就明说**，并列出搜过的词。要补充你自己的知识时，必须和知识库内容分开写，并标明"以下不来自知识库"。

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

## 2. 抽词

从问题里抽出 3 到 8 个检索词：

- 核心名词和报错原文里的关键片段；
- **同义词，以及中英文两种写法**（例如 `缓存` 和 `cache`，`插件` 和 `plugin`，`派活` 和 `子代理`、`subagent`、`委托`）；
- 工具名、命令名、库名照原样保留。

## 3. 检索

在同一个 shell 里：

```bash
python3 -B "$ROOT/scripts/kb.py" ask search 词1 词2 词3 --json
```

- 退出码 0：有命中，继续。
- 退出码 1：没有命中。先换一组词（更宽泛的上位词、其他同义词）再试**一次**；还是没有，就按第 4 条硬约束回答。
- 退出码 2：原样转述错误和修复提示，然后停下。

## 4. 读候选页面

- 按返回顺序，完整读前 3 到 5 页（路径是知识库根目录相对路径，知识库根目录在输出的 `vault` 字段里）。
- 看每页的 `status`：`superseded` 的页面已被 `superseded_by` 取代，要去读取代它的那一页。
- 看每条命中的 `zone`，按硬约束第 2 条区分现行结论和历史。
- 只有在需要核对原始证据时，才去读页面 `raw` 指向的 inbox 原文。

## 5. 回答

结构：

1. **直接回答问题**，一两句话，只用 `current` 区域的结论。
2. **依据**：逐条列出要点，每条后面附出处链接，写成 `[页面标题](<vault>/wiki/…/xxx.md)` 这种绝对路径链接，方便用户点开。
3. **历史与分歧**（有才写）：被推翻的旧结论、尚有争议的地方，并注明日期和出处。
4. **知识库之外**（有才写）：你自己的补充，明确标注"以下不来自知识库"。

检索词和命中页数在回答末尾用一行简短交代，例如："检索词：缓存、cache、插件、plugin；命中 2 页。"
