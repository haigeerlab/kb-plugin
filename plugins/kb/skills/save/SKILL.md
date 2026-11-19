---
name: save
description: 用户刚解决了一个问题、做了一个技术决策或学到一条经验，说“/kb:save”“存进 kb”“把这个坑记下来”“沉淀一下”时使用：从当前会话提炼这一条经验，编译进 kb 知识库，给用户看预览，确认后写入。不用于保存外部文章或网页，也不用于批量处理 inbox。
---

# 把这条经验存进 kb

**三条硬约束，先于一切步骤：**

1. **不直接改知识库里的任何文件。** 只往草稿目录写，写入知识库一律通过 `kb.py save apply`。
2. **没有用户在本轮明确同意，不执行 apply。** “好的”“继续”这类泛泛的回答，如果针对的不是这份预览，不算同意。
3. **脱敏命中时不绕过。** 改写成抽象描述后重新 preview；确认是误报的，告诉用户可以在知识库根目录的 `redaction-allow.txt` 放行，由用户自己决定，不要替用户添加。

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

从输出的 `vault` 字段得到知识库路径，下面记为 `$VAULT`。doctor 失败时原样转述修复提示，然后停下。

## 2. 确定要存哪一条

- 用户在命令后附了说明，就以说明为准。
- 没有说明时，从当前会话里找"已经解决、已经验证"的经验：bug 的症状、原因、解法，技术决策及其理由，可复用的做法。
- 找到不止一条时，列出来（每条一句话）让用户挑，**一次 save 只存一条**。
- 这条经验已经被知识库完整收录，或者没有长期价值时，直接说明，并建议不保存；用户仍然要求保存，就按"没有新内容"处理。
- 还没被验证的结论（比如"可能是缓存问题"）不要写成结论。要么问用户，要么在页面里明确标注"未验证"。

## 3. 读约定和目录

- 读 `$VAULT/SCHEMA.md`（本会话读过就不必重读），它是目录、frontmatter、章节、链接、标注块和敏感内容的权威约定。
- 读 `$VAULT/index.md`。

## 4. 检索已有知识（判"新建"之前必须做完两步）

1. 在 index 里找相关条目。
2. 用这条经验的关键词做全文搜索，**同时带上同义词和中英文术语**（例如 `缓存`、`cache`；`插件`、`plugin`；报错原文里的关键片段）：

   ```bash
   rg -n -i -e '关键词1' -e 'keyword2' -e '同义词' "$VAULT/wiki"
   ```

3. 把命中的候选页面完整读一遍。

只有 index 和全文搜索都没有找到同主题的页面时，才能判为"新建"；回答里要说明搜了哪些词。

## 5. 选处置

| 处置 | 条件 | 怎么写 |
|---|---|---|
| 新建 | 没有同一核心结论的页面 | 按类型从 `$VAULT/templates/<类型>.md` 复制模板，填写全部必备章节 |
| 并入 | 已有页面讲的是同一核心结论，这次补充了新的事实、版本或场景 | 把原页面复制进草稿再修改：补内容，`raw` 追加新 inbox 路径，刷新 `updated` |
| 冲突 | 新经验推翻了已有结论 | 原页面复制进草稿：旧结论**整段移进** `> [!outdated] YYYY-MM-DD → [现行结论标题](#锚点)` 块，新结论写成正文；说不清谁对时，把各方说法连同出处写进 `> [!disputed]` 块 |
| 没有新内容 | 知识库已经完整覆盖 | 只写 inbox 条目和 log，不改 wiki 和 index |

类型选择：`pitfall`（坑：症状、原因、解法）、`decision`（决策：背景、选项、决定、理由、后果）、`pattern`（可复用的做法）、`tech`（技术主题）、`project`（项目枢纽页）。拿不准时优先 `pitfall` 或 `decision`。

## 6. 写草稿

```bash
DRAFT="$(mktemp -d "${TMPDIR:-/tmp}/kb-save-XXXXXX")"
```

草稿目录的结构和知识库一一对应，只放这次要新建或修改的文件（修改的文件放完整的新内容）。

**inbox 条目**（必须恰好一个新文件）：`$DRAFT/inbox/YYYY-MM-DD-<英文-kebab-slug>.md`，日期用今天的本地日期。

```markdown
---
captured: YYYY-MM-DD
source: session
host: claude-code
title: 一句话中文标题
project: proj-xxx
---
## 背景
……
## 过程与证据
……（命令、版本号、报错原文、数字，从会话里逐字摘录）
## 结论
……
```

- `host`：在 Claude Code 里写 `claude-code`，在 Codex 里写 `codex`。`project` 只在有项目代号时写，没有就删掉这一行。frontmatter 里**不要写行内注释**，解析器会把注释当成值。
- 这是后面页面引用的"原文"：页面里要写的每个数字、日期、版本号、引用，都必须在这里**逐字**出现，否则 preview 会报 `evidence`。
- 是整理过的摘录，不是会话全文；只写和这条经验有关的内容。
- 遵守 SCHEMA 的敏感内容禁写项：项目用代号，不写客户名、内部域名和地址、密钥、业务数据。

**wiki 页面**：

- frontmatter 的 `raw` 列出本次的 inbox 路径（并入、冲突时追加，不删除原有的）；`created` 新建时写今天，`updated` 写今天。
- 链接一律用相对路径的 Markdown 链接，比如 `[标题](../pitfalls/xxx.md)`，**不用** `[[...]]`。
- 有项目代号且 `wiki/projects/` 下已有该项目的枢纽页时，在它的"相关坑"或"相关决策"一节加一条链接（把枢纽页也放进草稿）。

**index.md**：把 `$VAULT/index.md` 复制进草稿，在对应类型一节新增或更新一行：`- [标题](wiki/<目录>/<文件>.md) — 一句话摘要 · YYYY-MM-DD`。

**log.md**：把 `$VAULT/log.md` 复制进草稿，在**末尾**追加：

```markdown
## [YYYY-MM-DD] save | 标题

处置：新建 / 并入 / 冲突 / 没有新内容；一句话说明改了什么。
```

处置是"没有新内容"时，这一行**必须写出本次 inbox 条目的路径**，例如 `处置：没有新内容；已由 wiki/pitfalls/xxx.md 覆盖，原文见 inbox/2026-11-19-xxx.md。`。lint 靠这个路径区分"已经处理过的 inbox"和"还没编译的积压"。

## 7. 预览

```bash
python3 -B "$ROOT/scripts/kb.py" save preview "$DRAFT"
```

- 退出码 1：按报出的问题改草稿，再跑一次。格式类问题自己修好，不必拿给用户看。
- 脱敏命中：按第 3 条硬约束处理。
- 退出码 2：原样转述，然后停下。

## 8. 交给用户确认

preview 通过后，在回复正文里给出：

1. 处置结果和理由（判"新建"时说明搜过哪些词）；
2. 新建、修改的文件列表；
3. **完整的 diff**（原样贴出，不要只给摘要）；
4. 项目代号替换了几处；
5. 预览指纹。

然后问用户是否写入。用户要求修改的，改草稿后回到第 7 步。

## 9. 写入

用户在本轮明确同意后：

```bash
python3 -B "$ROOT/scripts/kb.py" save apply "$DRAFT" --confirm <指纹>
```

- 退出码 3：说明知识库或草稿在预览之后发生了变化，回到第 7 步重新预览，再给用户确认。
- 其他失败：原样转述，不要手动去改知识库。

## 10. 报告

报告提交号和改动的文件，然后删除草稿目录（`rm -r "$DRAFT"`，确认变量非空、路径在临时目录下再删）。不要 push。
