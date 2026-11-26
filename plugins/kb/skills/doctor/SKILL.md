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

doctor 只检查配置文件同目录下 `blocklist.txt`、`aliases.json` 是否存在，绝不读取这两个文件的内容。存在时显示「通过」；缺失时显示「提醒」，不影响整体通过状态和退出码。缺少 `blocklist.txt` 表示本地黑名单拦截规则不生效；缺少 `aliases.json` 表示真实名称到项目代号的替换规则不生效。JSON 中对应检查保留 `name`、`ok`、`message`，`ok` 恒为 `true`；缺失或符号链接目标不存在时标记 `level: "warn"`。

需要空模板时，先预览（支持 `--json`）：

```bash
python3 -B "$ROOT/scripts/kb.py" config init-redaction
```

原样转述将创建和将跳过的文件，取得用户确认后才执行：

```bash
python3 -B "$ROOT/scripts/kb.py" config init-redaction --confirm
```

命令只创建缺失文件：新文件权限 `0600`，新目录权限 `0700`；已有文件（包括符号链接）不读取、不覆盖、不修改。`blocklist.txt` 只有格式说明注释，`aliases.json` 为 `{}`，两者初始均无规则。内容由用户自己填写：黑名单一行一个客户名、品牌或公司域名，不区分大小写、按子串匹配，`#` 开头为注释；代号映射格式为 `{"真实名称": "proj-xxx"}`，JSON 不能写注释。不要代写真实名称，不要将这两个本地规则文件放进任何仓库。设置 `KB_CONFIG` 时，模板跟随该配置文件所在目录。
