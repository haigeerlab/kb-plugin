#!/usr/bin/env python3
"""Command dispatcher for the kb plugin."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from kblib import KbError
from kblib.config import (config_path, load_aliases, load_blocklist, read_optional_text,
                          resolve_vault, set_vault)
from kblib.doctor import diagnose
from kblib.checks import check as check_vault
from kblib.init import initialize
from kblib.redaction import apply_aliases, mask_text, parse_allowlist, scan
from kblib.vault import Vault


class ChineseParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = "命令与参数"
        self._optionals.title = "选项"
        self.add_argument("-h", "--help", action="help", help="显示帮助并退出")

    def format_help(self):
        return super().format_help().replace("usage: ", "用法：", 1)

    def error(self, message):
        raise KbError(
            "命令或参数无效。用法：kb.py doctor [--json]；"
            "kb.py config set-vault <路径> [--confirm] [--json]；"
            "kb.py init [--confirm] [--json]；kb.py check [--json] [路径 ...]；"
            "kb.py redact <文件|-> [--json | --apply-aliases]。运行 --help 查看帮助。"
        )


def build_parser():
    parser = ChineseParser(prog="kb.py", description="kb 插件自检、知识库配置、初始化、契约检查与脱敏扫描")
    commands = parser.add_subparsers(dest="command", required=True, metavar="子命令")
    doctor = commands.add_parser("doctor", help="检查配置与知识库目录")
    doctor.add_argument("--json", action="store_true", help="输出 JSON 对象")
    config = commands.add_parser("config", help="配置知识库位置")
    actions = config.add_subparsers(dest="action", required=True, metavar="配置命令")
    setter = actions.add_parser("set-vault", help="预览或写入知识库位置")
    setter.add_argument("path", metavar="路径", help="已存在的知识库目录")
    setter.add_argument("--confirm", action="store_true", help="确认写入配置；默认只预览")
    setter.add_argument("--json", action="store_true", help="输出 JSON 对象")
    initializer = commands.add_parser("init", help="预览或初始化知识库骨架")
    initializer.add_argument("--confirm", action="store_true", help="确认创建；默认只预览")
    initializer.add_argument("--json", action="store_true", help="输出 JSON 对象")
    checker = commands.add_parser("check", help="只读检查知识库契约")
    checker.add_argument("--json", action="store_true", help="输出 JSON 对象")
    checker.add_argument("paths", nargs="*", metavar="路径", help="相对知识库根目录的页面或目录；默认全部")
    redactor = commands.add_parser('redact', help='替换项目代号并扫描敏感内容，不写文件')
    redactor.add_argument('path', metavar='文件|-', help='草稿文件路径，或 - 从标准输入读取')
    output = redactor.add_mutually_exclusive_group()
    output.add_argument('--json', action='store_true', help='输出 JSON 扫描结果')
    output.add_argument('--apply-aliases', action='store_true', help='安全时输出替换后的文本，替换数写到标准错误')
    return parser


def redact(args, blocklist):
    aliases = load_aliases()
    root = resolve_vault().resolve() if config_path().exists() else None
    path = '<stdin>' if args.path == '-' else args.path
    try:
        text = sys.stdin.read() if args.path == '-' else Path(args.path).read_text(encoding='utf-8')
        if root is not None and args.path != '-':
            target = Path(args.path).resolve()
            if target.is_relative_to(root):
                path = target.relative_to(root).as_posix()
    except (OSError, UnicodeError, ValueError, RuntimeError):
        raise KbError('无法读取待扫描内容，需要普通文件或 UTF-8 标准输入') from None
    text, count = apply_aliases(text, aliases)
    allow_entries, errors = (parse_allowlist(read_optional_text(root / 'redaction-allow.txt'))
                             if root is not None else (set(), []))
    findings = errors + scan(text, path, blocklist, allow_entries)
    result = {'ok': not findings, 'replaced': count,
              'findings': [{**asdict(f), 'code': 'redaction', 'path': mask_text(f.path, blocklist)}
                           for f in findings]}
    return result, text


def print_redaction(result, stream):
    print(f"已替换 {result['replaced']} 处项目代号。", file=stream)
    for finding in result['findings']:
        print(f"{finding['path']}:{finding['line']} [redaction] {finding['category']}："
              f"{finding['masked']}（第 {finding['column']} 列）", file=stream)
    print('脱敏扫描通过，0 个问题。' if result['ok'] else
          f"脱敏扫描发现 {len(result['findings'])} 个问题。", file=stream)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else None
    is_doctor = command == "doctor"
    redacted_text = None
    blocklist = []
    try:
        args = build_parser().parse_args(argv)
        if args.command in ('check', 'redact'):
            blocklist = load_blocklist()
        if args.command == "doctor":
            result = diagnose()
        elif args.command == "init":
            result = initialize(args.confirm)
        elif args.command == "check":
            findings = check_vault(Vault.load(args.paths))
            result = {"ok": not findings, "findings": [asdict(finding) for finding in findings]}
        elif args.command == 'redact':
            result, redacted_text = redact(args, blocklist)
        else:
            result = set_vault(args.path, args.confirm)
        exit_code = 0 if result["ok"] else 1
    except KbError as error:
        message = mask_text(str(error), blocklist) if command in ('check', 'redact') else str(error)
        result = {"ok": False, "config": str(config_path()), "error": message}
        if command in ('check', 'redact'):
            result = {"ok": False, "findings": []}
            if command == 'redact':
                result['replaced'] = 0
            if "--json" in argv:
                print(message, file=sys.stderr)
            else:
                result["error"] = message
        elif command == "init":
            result.update(vault=None, create=[], skip=[], git_init=False, written=False)
        elif is_doctor:
            result.update(vault=None, checks=[])
        else:
            result.update(content=None, written=False)
        exit_code = error.exit_code
    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False))
    elif exit_code == 2:
        print(result["error"], file=sys.stderr)
    elif command == 'redact':
        if args.apply_aliases:
            print_redaction(result, sys.stderr)
            if result['ok']:
                sys.stdout.write(redacted_text)
        else:
            print_redaction(result, sys.stdout)
    elif command == "init":
        print(f"{'已初始化' if result['written'] else '初始化预览'}：{result['vault']}")
        for path in result['create']:
            print(f"{'已创建' if result['written'] else '将创建'}：{path}")
        for path in result['skip']:
            print(f"跳过（已存在，不覆盖）：{path}")
        if result['git_init']:
            print("git init：" + ("已执行" if result['written'] else "将执行"))
        else:
            print("git init：跳过，知识库已是 git 仓库")
        if not result['written']:
            print("尚未写入文件；确认后在同一命令后追加 --confirm。")
    elif command == "check":
        for finding in result['findings']:
            print(f"{finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
        print("契约检查通过，0 个问题。" if result['ok'] else f"契约检查发现 {len(result['findings'])} 个问题。")
    elif is_doctor:
        print(f"配置文件：{result['config']}\n知识库：{result['vault']}")
        for check in result["checks"]:
            print(f"{'通过' if check['ok'] else '失败'}：{check['message']}")
        print("自检通过。" if result["ok"] else result["error"])
    else:
        print(f"{'已写入配置' if result['written'] else '预览，将写入配置'}：{result['config']}")
        print(json.dumps(result["content"], ensure_ascii=False, indent=2))
        if not result["written"]:
            print("尚未写入文件；确认后在同一命令后追加 --confirm。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
