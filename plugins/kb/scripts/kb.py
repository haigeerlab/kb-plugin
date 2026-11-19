#!/usr/bin/env python3
"""Command dispatcher for the kb plugin."""

import argparse
import json
import sys

from kblib import KbError
from kblib.config import config_path, set_vault
from kblib.doctor import diagnose


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
            "kb.py config set-vault <路径> [--confirm] [--json]。运行 --help 查看帮助。"
        )


def build_parser():
    parser = ChineseParser(prog="kb.py", description="kb 插件自检与知识库位置配置")
    commands = parser.add_subparsers(dest="command", required=True, metavar="子命令")
    doctor = commands.add_parser("doctor", help="检查配置与知识库目录")
    doctor.add_argument("--json", action="store_true", help="输出 JSON 对象")
    config = commands.add_parser("config", help="配置知识库位置")
    actions = config.add_subparsers(dest="action", required=True, metavar="配置命令")
    setter = actions.add_parser("set-vault", help="预览或写入知识库位置")
    setter.add_argument("path", metavar="路径", help="已存在的知识库目录")
    setter.add_argument("--confirm", action="store_true", help="确认写入配置；默认只预览")
    setter.add_argument("--json", action="store_true", help="输出 JSON 对象")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    is_doctor = bool(argv and argv[0] == "doctor")
    try:
        args = build_parser().parse_args(argv)
        result = diagnose() if is_doctor else set_vault(args.path, args.confirm)
        exit_code = 0 if result["ok"] else 1
    except KbError as error:
        result = {"ok": False, "config": str(config_path()), "error": str(error)}
        if is_doctor:
            result.update(vault=None, checks=[])
        else:
            result.update(content=None, written=False)
        exit_code = error.exit_code
    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False))
    elif exit_code == 2:
        print(result["error"], file=sys.stderr)
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
