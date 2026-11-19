#!/usr/bin/env python3
"""Check the shared metadata of both plugin hosts."""

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    path = ROOT / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ValueError(f"无法读取清单或 JSON 无效：{path}") from None
    if not isinstance(data, dict):
        raise ValueError(f"清单必须是 JSON 对象：{path}")
    return data


def check_hooks():
    directory = ROOT / 'plugins/kb/hooks'
    paths = [directory / name for name in ('hooks.json', 'hooks.json.draft')
             if (directory / name).exists()]
    if len(paths) > 1:
        raise ValueError('hooks.json 与 hooks.json.draft 不能同时存在')
    if not paths:
        return
    data = load(paths[0].relative_to(ROOT))
    events = data.get('hooks')
    if not isinstance(events, dict) or set(events) != {'SessionEnd'}:
        raise ValueError('采集 hook 只能注册 SessionEnd 事件')
    groups = events['SessionEnd']
    if not isinstance(groups, list) or not groups:
        raise ValueError('SessionEnd 必须包含非空 hook 分组数组')
    for group in groups:
        if not isinstance(group, dict) or 'matcher' in group:
            raise ValueError('SessionEnd 分组必须是对象且不能设置 matcher')
        hooks = group.get('hooks')
        if not isinstance(hooks, list) or not hooks:
            raise ValueError('SessionEnd 分组必须包含非空 hooks 数组')
        for hook in hooks:
            if not isinstance(hook, dict) or hook.get('type') != 'command':
                raise ValueError('SessionEnd hook 的 type 必须为 command')
            timeout = hook.get('timeout')
            if type(timeout) not in (int, float) or not 0 < timeout <= 5:
                raise ValueError('SessionEnd hook 的 timeout 必须为正数且不超过 5 秒')
            command = hook.get('command')
            if (not isinstance(command, str)
                    or not re.search(r'''scripts/kb\.py["']?\s+capture\s+hook\b''', command)):
                raise ValueError('SessionEnd 命令必须引用 scripts/kb.py capture hook')
    if not (ROOT / 'plugins/kb/scripts/kb.py').is_file():
        raise ValueError('SessionEnd 引用的 scripts/kb.py 不存在')


def check():
    marketplace = load(".claude-plugin/marketplace.json")
    claude = load("plugins/kb/.claude-plugin/plugin.json")
    codex = load("plugins/kb/.codex-plugin/plugin.json")
    if marketplace.get("name") != "kb-marketplace":
        raise ValueError("市场名称必须为 kb-marketplace")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        raise ValueError("市场清单必须包含唯一的 kb 插件条目")
    entry = plugins[0]
    if entry.get("source") != "./plugins/kb":
        raise ValueError("市场清单的插件 source 必须为 ./plugins/kb")
    manifests = (entry, claude, codex)
    if any(manifest.get("name") != "kb" for manifest in manifests):
        raise ValueError("三份清单的插件名称必须一致且为 kb")
    for key, label in (("version", "版本"), ("description", "描述")):
        values = [manifest.get(key) for manifest in manifests]
        if any(not isinstance(value, str) or not value for value in values) or len(set(values)) != 1:
            raise ValueError(f"三份清单的{label}必须是非空字符串且完全一致")
    if marketplace.get("description") != entry["description"]:
        raise ValueError("市场描述与插件描述必须完全一致")
    skills = codex.get("skills")
    if not isinstance(skills, str) or not skills or not (ROOT / "plugins/kb" / skills).is_dir():
        raise ValueError("Codex 清单的 skills 必须指向已存在的目录")
    interface = load('plugins/kb/interface.json')
    version = interface.get('interface')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+', version):
        raise ValueError('interface.json 的 interface 必须为 主.次 版本号，例如 1.0')
    skill = interface.get('skill')
    match = re.fullmatch(r'kb:([a-z][a-z0-9-]*)', skill) if isinstance(skill, str) else None
    if match is None:
        raise ValueError('interface.json 的 skill 必须为 kb:<技能名>，例如 kb:ask')
    path = ROOT / 'plugins/kb/skills' / match[1] / 'SKILL.md'
    if not path.is_file():
        raise ValueError(f'interface.json 引用的 skill {skill} 不存在：{path}')
    check_hooks()


def main():
    try:
        check()
    except ValueError as error:
        print(f"清单检查失败：{error}", file=sys.stderr)
        return 1
    print("清单检查通过：插件名称、版本、描述一致，skills 目录与 interface.json 引用的技能存在，契约版本格式正确，采集 hook（如存在）有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
