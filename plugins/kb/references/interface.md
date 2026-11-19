# kb 检索接口契约

插件根目录的 [interface.json](../interface.json) 发布契约版本 `1.0`，JSON 输出 schema 为整数 `1`。
调用方只依赖确定性的检索层；`kb:ask` 是读取候选页面后综合回答的 skill。

## 探测与调用

1. 读取宿主的插件安装记录，选择已安装、已启用的 `kb`，取得插件根目录。Codex 可读取 `codex plugin list --available --json` 中 `installed` 的条目及其 `source.path`；Claude Code 使用其宿主插件记录。不要猜缓存路径、版本或按当前项目目录查找。
2. 读取该根目录下的 `interface.json`（本契约的机器可读文件），检查 `interface` 是否落在调用方支持的版本范围，例如 `>=1.0,<2.0`，并确认支持其中声明的 `schema: 1`。版本按主、次两个整数比较，不按字符串比较。字段说明见本文件。
3. 读不到插件记录、插件未启用、读不到契约文件、文件无法解析或版本不兼容时，静默跳过 kb 集成；对调用方视为未安装，不安装、不提示用户、不更改配置。
4. `search` 是相对插件根目录的参数模板。把 `scripts/kb.py` 解析为根目录下的绝对路径，把 `<term>`、`...` 替换为一个或多个关键词参数，不把省略号原样传入。使用参数数组调用，避免 shell 拼接。可追加 `--limit N`，默认 `10`，必须为正整数。

```bash
python3 -B /插件根目录/scripts/kb.py ask search --json 缓存 cache 插件 --limit 5
```

命令读取 `~/.config/kb/config.json`，设置 `KB_CONFIG` 可指定另一份配置；始终使用配置中的知识库，不依赖当前目录。检索不写文件、不调用模型、不提交、不修改 Git 状态。

## 输出字段（schema 1）

正常检索时 stdout 是一个 JSON 对象：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `schema` | 整数 | 固定为 `1` |
| `ok` | 布尔 | 检索执行成功为 `true`，没有命中也为 `true` |
| `vault` | 字符串 | 知识库绝对路径 |
| `terms` | 字符串数组 | 实际检索词，按输入顺序保留；大小写等价的重复词只保留第一个写法 |
| `pages` | 对象数组 | 按下述规则排序的候选页面，无命中时为空数组 |
| `truncated` | 布尔 | 候选页数超过 limit、存在未返回页面时为 `true`；命中行截断不影响它 |

每页字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `path` | 字符串 | 相对知识库根目录的 `wiki/` Markdown 页面路径 |
| `title` | 字符串 | 页面 frontmatter 的标题 |
| `type` | 字符串 | 页面类型，如 `pitfall`、`decision`、`tech`、`pattern`、`project` |
| `status` | 字符串 | 页面状态，如 `current`、`superseded` |
| `superseded_by` | 字符串或 null | frontmatter 的取代页面路径，未填写时为 null |
| `updated` | 字符串 | frontmatter 的更新日期，格式 `YYYY-MM-DD` |
| `raw` | 字符串数组 | frontmatter 中的出处路径；可从知识库根目录读取对应原文 |
| `score` | 整数 | 命中的不同词数 × 2 + 标题命中的不同词数 × 3 + index 中该页条目行命中的不同词数 × 1 |
| `matched_terms` | 字符串数组 | 页面正文命中的不同检索词，顺序及写法与 `terms` 一致 |
| `hits` | 对象数组 | 最多 20 条命中行，按原始行号升序 |

每条 hit 为 `{line, zone, text}`：`line` 是从 1 开始的原文件行号（包含 frontmatter 行数）；`text` 是命中行去首尾空白后最多 200 个字符的文本；`zone` 为以下之一：

- `current`：普通正文。
- `outdated`：`[!outdated]` 标注块内；页面 `status: superseded` 时整页命中均为此值。
- `disputed`：`[!disputed]` 标注块内。

代码块内同样匹配，区域取其所属标注块；代码中的伪标注不创建区域。frontmatter 不产生命中，标题字段仅对已命中的页面加权。
多词按任意一个命中匹配，不区分大小写，中英文混排与正则特殊字符均作为字面量子串处理。
仅检索 `wiki/` 下的 `.md` 页面；index.md 不作为独立结果，也不单独产生候选页，只给其链接对应的已命中页面加权。

所有命中都为 outdated 的页面排在任何含 current 或 disputed 命中的页面之后；各组内按 score 降序、updated 新到旧、path 升序排列。排序与计分基于全部命中，再截取页面及其前 20 条命中行。
调用方应读取候选页面全文，再依据区域使用内容；outdated 只可作为历史，disputed 应呈现各方说法。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 检索成功，有命中，输出 schema 1 JSON |
| `1` | 检索成功，没有命中，仍输出 schema 1 JSON，`ok: true`、`pages: []`、`truncated: false` |
| `2` | 配置或用法错误，如未配置知识库、没有词、limit 非正整数；`--json` 输出含 `ok: false` 和中文 `error` 的错误对象，不属于正常检索 schema |

未指定 `--json` 时输出中文文本，逐页给出标题、路径、状态、得分和带区域的命中行。程序调用方应使用 `--json`，先判断退出码，再解析相应输出。

## 版本规则

`interface` 使用 `主.次`，从 `1.0` 开始；`schema` 是正常检索 JSON 输出结构的整数版本。
兼容的新增能力可以升级次版本。输出结构发生破坏性变更（如删除或重命名字段、改变字段类型或既有语义）必须升级契约主版本号，并升级输出 schema 版本；调用方必须先按支持范围判断，再调用。不能只改代码而维持原契约版本。
