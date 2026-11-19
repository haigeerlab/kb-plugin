---
name: doctor
description: 用户需要检查 kb 插件配置、确认知识库位置，或排查知识库未配置及目录无法访问时使用。
---

先在 bash 中执行下面的插件根目录解析片段，并在同一个 shell 中运行后面的自检命令。
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

根目录解析成功后执行：

```bash
python3 -B "$ROOT/scripts/kb.py" doctor
```

原样转述标准输出、标准错误与退出码。失败时原样转述输出中的修复命令或修复提示。
缺少配置时，提示用户用 `config set-vault <路径>` 先预览，确认后追加 `--confirm`；不替用户选择知识库或写入配置。
退出码 0 表示通过，1 表示检查发现问题，2 表示配置或用法错误。
