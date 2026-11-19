<!-- spec-guard: review approved 5237a28c6233 -->

# Spec: plugin-shell

## Objective

能力图第 1 个模块。给 kb 搭一个双宿主外壳：同一个插件目录既能装进 Claude Code，也能装进 Codex，两边共用同一套 skills 和脚本；同时解决"在任何项目目录里都能找到同一个知识库"这件事。后续模块（vault-contract、save、ask、lint……）的 skill 和脚本都放进这个外壳，本模块不实现任何知识操作。

用户：你本人，在 Claude Code 或 Codex 的任意项目会话里使用 kb。

成功的样子：
- 两个宿主各执行一次安装命令，`kb:doctor` 就出现并能运行。
- 在任何目录下运行，`kb doctor` 都指向同一个知识库；没配置时明确报错、告诉你怎么配，绝不猜测路径。

## 要你确认的假设

1. **命令写法是 `/kb:save`，不是 `/kb save`。** Claude Code 的插件 skill 一律带命名空间，形如 `/<插件名>:<skill 名>`（本机 spec-guard、agent-relay 都是这样）。PRD 里写的 `/kb save` 在实现中统一成 `/kb:save`、`/kb:ask`、`/kb:lint`、`/kb:doctor`。日常也可以直接用自然语言说"把这个存进 kb"，由 skill 的描述触发。
2. **仓库布局照搬本机先例**（spec-guard、agent-relay 已经在两个宿主上跑通）：仓库根放 `.claude-plugin/marketplace.json`，插件本体放 `plugins/kb/`，里面放 `.claude-plugin/plugin.json` 和 `.codex-plugin/plugin.json` 两份清单，共用 `skills/`。
3. **Codex 能识别 `.claude-plugin/marketplace.json`，这一点待实测。** OpenAI 官方文档写的 Codex 市场文件位置是 `.agents/plugins/marketplace.json`，但 spec-guard 和 agent-relay 只有 `.claude-plugin/marketplace.json`，它们的 README 写着可以用 `codex plugin marketplace add` 安装。本模块用 AC3 实测；如果实测不认，就补一份 `.agents/plugins/marketplace.json`（官方格式），并在变更记录里写明。
4. **插件根目录的解析顺序照搬 spec-guard**：先 `CLAUDE_PLUGIN_ROOT`，再 `PLUGIN_ROOT`，最后查 `codex plugin list --available --json` 里已安装且已启用的 `kb`。全部失败就报错，不猜缓存版本。
5. **知识库位置写在配置文件里**：`~/.config/kb/config.json`，内容形如 `{"version": 1, "vault": "~/Documents/haigeerlab/kb"}`。环境变量 `KB_CONFIG` 可以指定另一份配置文件，只给测试用；不提供"按当前目录向上找知识库"的发现逻辑，避免在别的项目里误认。
6. **脚本只用 Python 3 标准库**，最低支持 3.9（本机是 3.10.7），不引入任何第三方依赖。测试用标准库 `unittest`。
7. **本模块不带 hook。** SessionEnd 采集是 session-capture 模块的事。

## Commands

```bash
# 测试（仓库根目录）
python3 -m unittest discover -s tests -v

# 清单一致性检查（两份 plugin.json 与 marketplace.json 的名称、版本、描述一致）
python3 -B scripts/check-manifests.py

# 自检（任何目录）
python3 -B plugins/kb/scripts/kb.py doctor
python3 -B plugins/kb/scripts/kb.py doctor --json

# 写入知识库位置（先预览，加 --confirm 才写）
python3 -B plugins/kb/scripts/kb.py config set-vault ~/Documents/haigeerlab/kb
python3 -B plugins/kb/scripts/kb.py config set-vault ~/Documents/haigeerlab/kb --confirm

# 本机安装（实测用，执行前先问你）
claude plugin marketplace add ~/Documents/haigeerlab/kb-plugin
claude plugin install kb@kb-marketplace
codex plugin marketplace add ~/Documents/haigeerlab/kb-plugin
codex plugin add kb@kb-marketplace
```

## Project Structure

```
kb-plugin/
├── .claude-plugin/marketplace.json     # 市场清单（kb-marketplace）
├── plugins/kb/
│   ├── .claude-plugin/plugin.json      # Claude Code 清单
│   ├── .codex-plugin/plugin.json       # Codex 清单：skills 指向 ./skills/
│   ├── skills/
│   │   └── doctor/SKILL.md             # /kb:doctor；后续模块在这里加 save、ask、lint
│   ├── scripts/
│   │   ├── kb.py                       # 唯一入口：子命令分发
│   │   └── kblib/
│   │       ├── config.py               # 配置读写与知识库定位
│   │       └── doctor.py               # 自检
│   └── references/
│       └── locate-plugin-root.md       # 各 skill 共用的插件根目录解析片段
├── scripts/check-manifests.py          # 开发期检查，不随插件分发
├── tests/                              # unittest
├── spec/  tasks/  docs/                # spec-guard 约定、PRD 与调研
└── README.md
```

## Code Style

```python
# plugins/kb/scripts/kblib/config.py
CONFIG_ENV = "KB_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "kb" / "config.json"


class VaultNotConfigured(KbError):
    exit_code = 2


def resolve_vault(environ: Mapping[str, str] = os.environ) -> Path:
    """Return the configured vault. Never guess: no cwd discovery, no defaults."""
    config_path = Path(environ.get(CONFIG_ENV) or DEFAULT_CONFIG)
    if not config_path.is_file():
        raise VaultNotConfigured(f"未找到配置 {config_path}；运行 kb.py config set-vault <路径> 设置知识库位置")
    ...
```

- 代码标识符和注释用英文；面向用户的输出（报错、预览、doctor 结果）用中文。
- 每个子命令都支持 `--json`，输出一个 JSON 对象，字段固定；文本输出给人看。
- 退出码：0 成功，1 检查发现问题，2 配置或用法错误。
- 所有写操作默认只预览，加 `--confirm` 才写。

## Testing Strategy

- `unittest`，测试放在 `tests/`，用 `KB_CONFIG` 加临时目录隔离，不碰真实的 `~/.config/kb`。
- 单元测试：配置解析的各种失败路径（文件不存在、JSON 损坏、版本不支持、vault 不存在、vault 不是目录、相对路径）。
- 根目录解析测试：在 PATH 前面放一个假的 `codex` 脚本，覆盖 `CLAUDE_PLUGIN_ROOT`、`PLUGIN_ROOT`、`codex plugin list`、全部失败四种情况。
- 清单测试：`check-manifests.py` 检查名称、版本、描述一致，以及 `.codex-plugin` 的 `skills` 路径存在。
- 两个宿主的真实安装是手动验收（AC2、AC3），结果记入 `tasks/plugin-shell/todo.md`。

## Boundaries

- **总是**：写操作先预览；配置缺失时报错并给出修复命令；所有测试用临时目录。
- **先问**：在真实的 Claude Code 和 Codex 里安装插件（会改你的宿主配置）；创建 GitHub 仓库或推送；写 `~/.config/kb/config.json`。
- **不做**：任何知识操作（save、ask、lint 在后续模块）；hook；按当前目录猜测知识库位置；第三方依赖；修改 kb 仓库和 `~/.config/kb/` 以外的任何文件。

## Success Criteria

- **AC1** `python3 -m unittest discover -s tests` 全部通过，覆盖上面测试策略里列出的所有失败路径。
- **AC2** Claude Code：`claude plugin marketplace add <本地路径>` 加 `claude plugin install kb@kb-marketplace` 之后，新会话里能看到并运行 `/kb:doctor`，输出知识库位置和自检结果。
- **AC3** Codex：`codex plugin marketplace add <本地路径>` 加 `codex plugin add kb@kb-marketplace` 之后，`codex plugin list` 显示 kb 已安装且已启用；新会话里能触发 doctor skill，并解析到正确的插件根目录。若 Codex 不认 `.claude-plugin/marketplace.json`，补官方格式的 `.agents/plugins/marketplace.json` 后此条通过。
- **AC4** 在 `kb-plugin`、`tab-leader`、`/tmp` 三个不同目录下运行 `kb.py doctor --json`，`vault` 字段相同。
- **AC5** 没有配置文件时，`doctor` 退出码为 2，报错里包含配置文件路径和 `config set-vault` 的用法；配置指向不存在的目录时同样退出 2。
- **AC6** `config set-vault` 不加 `--confirm` 时不写文件，只打印将写入的路径和内容；加 `--confirm` 后写入，`doctor` 通过。
- **AC7** `check-manifests.py` 通过；故意把某一份清单的版本改掉，它会报错并退出 1。
- **AC8** README 写清：安装（两个宿主）、命令清单（标注哪些还没实现）、知识库位置配置、卸载。

## Documentation impact

| 文档 | 动作 |
|---|---|
| `README.md` | 新建：安装、命令、配置、卸载 |
| `plugins/kb/references/locate-plugin-root.md` | 新建：后续各 skill 引用的根目录解析片段 |

## Open Questions

无。（Codex 是否认 `.claude-plugin/marketplace.json` 见假设 3，由 AC3 实测决定，不需要你现在回答。）

## 变更记录

- 2026-11-19 初稿。
- 2026-11-19 最终验收前：实测确认假设 3（Codex 认 `.claude-plugin/marketplace.json`），未改范围。记录一处宿主差异：Codex 读的是缓存里的 SKILL.md 副本。
