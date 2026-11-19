---
name: compile
description: 用户要批量整理 kb 知识库的积压时使用，例如“/kb:compile”“整理一下 kb 的 inbox”“把最近的会话里值得记的东西编译进 kb”，或者每周整理。处理两类来源：inbox 里还没进 wiki 的条目，以及候选会话队列里的历史会话。先给清单让用户挑，再一次给出全部预览让用户确认，最后逐条写入。
---

# 批量整理 kb 积压

**四条硬约束，先于一切步骤：**

1. **用户做两次决定，你不替用户做。** 第一次：在清单里挑出哪些要编译、哪些丢弃；第二次：确认要写入哪些预览。两次都要等用户在本轮明确回复。丢弃候选也要由用户决定。
2. **不直接改知识库里的任何文件。** 只写草稿目录，写入一律通过 `kb.py compile apply`。
3. **会话内容只通过 `candidates show` 读取**，不要直接打开会话记录文件。`show` 的输出已经打过码；输出里看到打码片段时，不要试图还原。
4. **每项独立写入，失败就停。** 一项失败时停下来报告，已经写入的项不回退；提交失败时按第 6 步处理。

## 1. 定位插件和知识库

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

然后在同一个 shell 里：

```bash
python3 -B "$ROOT/scripts/kb.py" doctor --json
```

从 `vault` 字段得到知识库路径，下面记为 `$VAULT`。读 `$VAULT/SCHEMA.md` 和 `$VAULT/index.md`（本会话读过就不必重读）。

## 2. 列清单（第一次决定）

```bash
python3 -B "$ROOT/scripts/kb.py" candidates list --json
```

对每一项先了解内容：

- **inbox 积压**：完整读该 inbox 文件。
- **候选会话**：`python3 -B "$ROOT/scripts/kb.py" candidates show <id>`。一个会话里可能有多条经验，也可能一条都没有。

然后给用户一张清单，每一行包括：编号、来源（积压 / 候选，候选附上项目目录和结束时间）、一句话内容、你的建议（**编译** / **丢弃** / **先留着**）及理由。即将过期的候选标出"即将过期"；已过期的只列出来说明一下，不再处理。一个会话里有多条经验时拆成多行，例如 3a、3b。

建议"丢弃"的标准：没有解决的问题、没有被验证的猜测、只是闲聊或纯操作记录、知识库里已经完整覆盖的内容。

问用户：要编译哪几项、丢弃哪几项。没提到的项保持原样。

## 3. 写草稿并批量预览（第二次决定）

对用户选中的每一项，**单独**建一个草稿目录：

```bash
DRAFT="$(mktemp -d "${TMPDIR:-/tmp}/kb-compile-XXXXXX")"
```

写法与 `/kb:save` 的第 4 到第 6 步相同：先检索已有知识（index 加全文搜索，带上同义词和中英文术语），再选处置（新建 / 并入 / 冲突 / 没有新内容），然后按模板写页面、更新 index 和 log。区别只有两点：

| 来源 | inbox | log 操作名 |
|---|---|---|
| inbox 积压 | **不新建** inbox 文件，页面 `raw` 引用已有的那条 | `compile` |
| 候选会话 | 新建**一条** inbox 摘录（`source: session`），承重事实从 `candidates show` 的输出里逐字摘出 | `compile` |

log 条目格式：`## [YYYY-MM-DD] compile | 标题`。处置为"没有新内容"时，正文写出 inbox 路径。

注意：后面的项要在前面的项**写入之后**才能 preview，因为它们改的是同一份 index 和 log。所以本步先把所有草稿写好；预览时先对第一项运行：

```bash
python3 -B "$ROOT/scripts/kb.py" compile preview "$DRAFT"
```

其余项的 index 和 log 草稿，等前一项写入后，在第 4 步按最新内容重新生成并 preview。

一次性在回复正文里给出：每一项的处置和理由、文件清单、页面和 inbox 的**完整内容或 diff**，第一项的指纹。说明后续项会在前一项写入后重新生成 index 和 log，并各自再出一次指纹。

问用户：确认写入哪几项。

## 4. 逐条写入

按顺序处理用户确认的项：

1. （第二项起）按当前知识库重新复制 index.md、log.md 到该项的草稿目录，加上本项的条目，然后运行 `compile preview`。如果页面内容和第 3 步给用户看过的不一样，停下来重新请用户确认；只有 index 和 log 变化时，可以继续。
2. 运行 `python3 -B "$ROOT/scripts/kb.py" compile apply "$DRAFT" --confirm <指纹>`。
3. 来源是候选会话的，这个会话的全部条目都处理完之后，运行 `candidates mark <id> --status compiled`。

用户在第 2 步选择丢弃的候选：`candidates mark <id> --status dropped`。

## 5. 报告

列出每项的结果（提交号，或者失败原因），然后删除草稿目录（确认变量非空、路径在临时目录下）。最后运行一次 `python3 -B "$ROOT/scripts/kb.py" lint`，告诉用户积压是否已经清掉。不要 push。

## 6. 失败处理

- 退出码 3：知识库在预览之后变了，回到该项的 preview。
- 报"文件已写入但提交失败；已记录待提交"：把报错里给出的 `commit-pending` 命令**原样**告诉用户，请用户在 Claude Code、终端或提权后的 Codex 里运行。**不要自己执行 `git add`、`git commit`，也不要去改 `.git` 或 `.kb-pending.json`。** 剩下的项暂停，等用户完成提交后再继续。
- 报"有待提交记录"：先请用户运行 `commit-pending`。
- 脱敏命中：改写成抽象描述后重新 preview；确认是误报的，告诉用户可以在 `redaction-allow.txt` 放行，由用户决定。
