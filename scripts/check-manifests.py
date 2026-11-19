#!/usr/bin/env python3
"""Check the shared metadata of both plugin hosts."""

import json
from pathlib import Path
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


def main():
    try:
        check()
    except ValueError as error:
        print(f"清单检查失败：{error}", file=sys.stderr)
        return 1
    print("清单检查通过：插件名称、版本、描述一致，skills 目录存在。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
