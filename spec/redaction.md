<!-- spec-guard: review approved fa960457fa32 -->

# Spec: redaction

## Objective

能力图第 3 个模块。在任何内容写进知识库之前做脱敏扫描：命中敏感内容就拒绝写入，并指出位置；项目真名自动替换成代号。落实 PRD 6.4"抽象化 + 脚本拦截"。

为什么必须在写入**之前**拦：inbox 一旦提交就不可改（vault-contract 的 `immutable` 检查），敏感内容一旦进了 inbox，就只能改写 git 历史才能清掉。所以本模块提供两道关：

1. **写入前**：save、compile、delegate-lessons 调用 `redact` 扫描草稿，命中就不写。
2. **兜底**：`kb check` 新增 `redaction` 检查，扫描整个知识库，防止有人手改或者绕过了第一道关。

用户：后续写入类模块（save、inbox-compile、delegate-lessons），以及你本人（手动跑 `kb check`）。

## 要你确认的假设

1. **内置规则只拦"有明确形态"的东西，宁可漏也不滥报。**
   - 密钥和凭证：私钥块（`-----BEGIN … PRIVATE KEY-----`）、AWS Access Key（`AKIA…`）、GitHub token（`ghp_`、`gho_`、`github_pat_` 等）、OpenAI 和 Anthropic key（`sk-…`、`sk-ant-…`）、Slack token（`xox…`）、JWT（三段 base64url）、`Bearer <长串>`、带账号密码的连接串（`scheme://user:pass@host`）、`password=`、`secret=`、`token=`、`api_key=` 这类赋值后面跟着非占位符的值。
   - 网络标识：IPv4 地址（`127.0.0.1`、`0.0.0.0` 和文档专用网段 `192.0.2.0/24`、`198.51.100.0/24`、`203.0.113.0/24` 除外）；内网形态的主机名（`.internal`、`.local`、`.corp`、`.lan`、`.intra` 结尾）；邮箱地址（`example.com`、`example.org` 等示例域名除外）。
   - **不做熵值检测**：误报太多，会让"一句话沉淀"变得很烦。
2. **公司相关的词放在本地黑名单里，不进库**：`~/.config/kb/blocklist.txt`，一行一个词，不区分大小写，按子串匹配，`#` 开头是注释。客户名、品牌、公司域名都写在这里。没有这个文件时只用内置规则，不报错。
3. **项目代号对照放在本地**：`~/.config/kb/aliases.json`，格式 `{"真实名称": "proj-xxx"}`。扫描前先把真名**自动替换**成代号，在预览里显示替换了几处，不需要你逐个确认（替换是确定性的，预览里看得到）。替换之后仍然残留真名的，按黑名单命中处理。
4. **误报的放行清单放在知识库里，而且不存原文**：知识库根目录 `redaction-allow.txt`，一行一条 `<文件路径> <命中内容的 sha256 前 16 位>  # 说明`。只有放行清单里写明的那一处命中才放行；换了文件、或者内容变了，就不再放行。清单进 git，放行记录可审计，同时不会把疑似密钥的原文写进库里。
5. **报错不回显敏感原文**：只显示类别、文件、行号、列号，以及打码后的片段（保留前 4 个字符，其余替换成 `*`）。避免脱敏工具本身把密钥打进终端日志和模型上下文。
6. **扫描范围**：`kb check` 扫描 `inbox/`、`raw/`、`wiki/`、`index.md`、`log.md`。代码块里的内容**同样扫描**，因为密钥最常出现的地方恰恰是贴进来的代码和日志。
7. **本模块不交付用户可见的 skill。** `redact` 是脚本命令和库函数，由后续写入模块调用；你需要时也可以手动跑。
8. **测试里的假密钥在运行时拼出来**，不以完整形态写进仓库，免得触发 GitHub 的推送保护和各种密钥扫描器。

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -B plugins/kb/scripts/kb.py redact <文件|->  [--json]            # 扫描，命中时退出 1
python3 -B plugins/kb/scripts/kb.py redact <文件|-> --apply-aliases     # 输出替换代号后的文本到 stdout（不写文件）
python3 -B plugins/kb/scripts/kb.py check                               # 现在包含 redaction 检查
```

`redact --json` 的输出：`{ok, replaced: <替换数>, findings: [{code: "redaction", category, path, line, column, masked}]}`；`category` 取 `secret`、`network`、`email`、`blocklist` 之一。

### 本地规则创建入口

`python3 -B plugins/kb/scripts/kb.py config init-redaction [--confirm] [--json]` 默认只预览 `config_path().parent` 下将创建的 `blocklist.txt`、`aliases.json`，不创建目录。用户确认后追加 `--confirm`，以 `O_CREAT|O_EXCL` 只创建缺失文件（`0600`），缺失目录以 `0700` 创建；已有文件及符号链接一律跳过，不读取、不覆盖、不修改。黑名单模板仅含注释，代号模板为 `{}` 加换行，加载后分别为空列表和空字典；实际规则由用户自己填写，映射格式 `{"真实名称": "proj-xxx"}` 在输出中说明，规则文件不得进入任何仓库。成功及失败 JSON 均含 `ok`、`config`、`create`、`skip`、`written`、`error`。

doctor 对上述两个文件只检查存在性，不读取内容。缺失时以「提醒」说明相应黑名单拦截或代号替换规则不生效，并给出创建命令；存在时显示「通过」。JSON 保留原有顶层字段及检查项的 `name`、`ok`、`message` 字段，新增检查名为 `blocklist`、`aliases`；两项的 `ok` 恒为 `true`（`ok: false` 仍只表示失败），缺失或符号链接目标不存在时带 `level: "warn"`，存在时带 `level: "info"`；提醒不影响整体 `ok` 和退出码。这不验证文件格式，也不代表空模板已包含有效业务规则。

## Project Structure（本模块新增或修改）

```
plugins/kb/scripts/kblib/
├── redaction.py     # 规则、扫描、代号替换、放行清单；纯函数
├── checks.py        # 修改：新增 check_redaction，注册进 CHECKS
└── config.py        # 修改：本地 blocklist.txt、aliases.json 的路径解析（跟随 KB_CONFIG 所在目录，便于测试隔离）
plugins/kb/scripts/kb.py          # 修改：新增 redact 子命令
plugins/kb/templates/SCHEMA.md    # 修改："禁止写入的敏感内容"一节补上本地黑名单、代号、放行清单的说明
tests/test_redaction.py
```

## Code Style

延续前两个模块。规则写成一张表，每条规则一行：`Rule(category, name, pattern, allow=None)`，新增规则只加一行，不改扫描逻辑。

## Testing Strategy

- 每条内置规则至少一个命中用例和一个不该命中的用例（占位符如 `password=<your-password>`、`sk-xxx`，示例 IP、示例域名）。
- 黑名单：不区分大小写、子串匹配、注释行、文件缺失时不报错。
- 代号替换：多个代号、名称互相包含时最长的优先、替换后残留真名按黑名单命中。
- 放行清单：同一文件同一内容放行；换文件或改内容后不再放行；清单格式错误时报 `redaction` 并给出行号。
- 打码：所有输出里（文本和 JSON）都不出现完整的假密钥。
- `kb check` 集成：合法样例（valid、dispatch）仍然 0 问题；在 inbox 里放一个假密钥，报 `redaction`。
- 假密钥在测试运行时拼接生成。

## Boundaries

- **总是**：命中就拒绝，不自动删除或改写敏感内容（只有代号替换是自动的）；输出打码。
- **先问**：创建或修改你真实的 `~/.config/kb/blocklist.txt`、`aliases.json`（里面是公司信息，由你自己写；我只提供格式说明和空模板）。
- **不做**：熵值检测；调用模型判断"是否敏感"；联网查询；改写 git 历史；扫描知识库以外的文件。

## Success Criteria

- **AC1** 单元测试全部通过，覆盖上面 Testing Strategy 的每一项。
- **AC2** `redact` 对含假密钥的输入退出 1，输出里有类别、行号、列号和打码片段，**完整假密钥在 stdout 和 stderr 里都不出现**。
- **AC3** 配置了 `aliases.json` 时，`--apply-aliases` 输出替换后的文本，并报告替换了几处；替换后的文本再跑 `redact` 不命中黑名单。
- **AC4** `kb check` 含 `redaction` 检查：valid 和 dispatch 两套样例仍然 0 问题；你真实的知识库仍然 0 问题。
- **AC5** 放行清单能精确放行一处误报，换文件或改内容后失效。
- **AC6** 用一段真实形态的会话摘录做端到端演示（内容由测试拼出：含一个假的 GitHub token、一个内网 IP、一个黑名单里的公司名、一个项目真名）：`redact` 报出 3 处命中，替换 1 处代号，并且都定位准确。
- **AC7** SCHEMA.md 模板和 README 写清三个本地文件（blocklist、aliases、放行清单）的位置、格式和作用。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `plugins/kb/templates/SCHEMA.md` | 修改：敏感内容一节 |
| `README.md` | 修改：`redact` 用法、本地文件说明 |

已初始化的真实知识库里的 SCHEMA.md 不会自动更新（init 不覆盖已有文件）。本模块验收时，由我生成改动预览，你确认后再更新知识库里的那一份。

## Open Questions

无。

## 变更记录

- 2026-11-19 初稿。
- 2026-11-26：补充本地规则空模板创建入口与 doctor 存在性提醒。原因：缺失规则静默为空且用户缺少创建入口。来源：插件功能盘点第六节缺口 2，用户 2026-11-26 同意按方案实现。
