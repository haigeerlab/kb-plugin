---
name: init
description: 用户要初始化已配置的 kb 知识库、预览将创建的目录和模板，或补齐缺失骨架时使用。
---

先在 bash 中执行下面的根目录解析片段，并在同一个 shell 中执行预览。
解析失败时停止，原样转述原因，不猜测插件目录或知识库位置。

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

先预览，不写入：

```bash
python3 -B "$ROOT/scripts/kb.py" init
```

原样转述标准输出、标准错误与退出码，包括每个将创建的文件、跳过的已有文件，以及是否将执行 git init。
缺少配置时原样转述配置修复提示，不替用户选择目录或写入配置。
等待用户明确同意本次预览后，才在同一命令加 --confirm；用户尚未同意时不得写入，也不得执行 git init。

得到明确同意后，重新解析插件根目录，在同一个 shell 中执行：

```bash
python3 -B "$ROOT/scripts/kb.py" init --confirm
```

原样转述结果。已有文件只跳过，绝不覆盖；本 skill 不提交知识库。
命令支持 --json；退出码 0 表示成功，2 表示配置、用法或初始化错误。
