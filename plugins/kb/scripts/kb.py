#!/usr/bin/env python3
"""Command dispatcher for the kb plugin."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import date
import io
import json
import os
from pathlib import Path
import sys

from kblib import KbError, candidates, capture, delegate_lessons, semantic
from kblib.ask import search
from kblib.compile import compile as compile_draft
from kblib.config import (config_path, init_redaction, load_aliases, load_blocklist, read_optional_text,
                          resolve_vault, set_vault, set_capture)
from kblib.doctor import diagnose
from kblib.checks import check as check_vault
from kblib.init import initialize
from kblib.lint import (fix as lint_fix, print_fix as print_lint_fix,
                        report as lint_report, print_report as print_lint_report)
from kblib.redaction import apply_aliases, mask_text, parse_allowlist, scan
from kblib.save import empty_result as empty_save_result, save
from kblib.vault import Vault, today
from kblib.writer import commit_pending, empty_pending_result


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
            "kb.py config init-redaction [--confirm] [--json]；"
            "kb.py init [--confirm] [--json]；kb.py check [--json] [路径 ...]；"
            "kb.py redact <文件|-> [--json | --apply-aliases]；"
            "kb.py save preview <草稿目录> [--json]；"
            "kb.py save apply <草稿目录> --confirm <指纹> [--json]；"
            "kb.py candidates add|list|show|mark|scan-delegate …；"
            "kb.py capture status [--json]；kb.py capture hook；"
            "kb.py config set-capture --enabled true|false [--min-user-messages N] [--ignore-dir 路径 ...] [--confirm] [--json]；"
            "kb.py compile preview|apply <草稿目录> …；"
            "kb.py commit-pending [--json]；"
            "kb.py ask search <词> [<词> ...] [--limit N] [--json]。运行 --help 查看帮助。"
        )


def build_parser():
    parser = ChineseParser(prog="kb.py", description="kb 插件自检、知识库配置、初始化、契约检查、脱敏扫描、知识保存、编译、检索与体检")
    commands = parser.add_subparsers(dest="command", required=True, metavar="子命令")
    doctor = commands.add_parser("doctor", help="检查配置与知识库目录")
    doctor.add_argument("--json", action="store_true", help="输出 JSON 对象")
    config = commands.add_parser("config", help="配置知识库位置")
    actions = config.add_subparsers(dest="action", required=True, metavar="配置命令")
    setter = actions.add_parser("set-vault", help="预览或写入知识库位置")
    setter.add_argument("path", metavar="路径", help="已存在的知识库目录")
    setter.add_argument("--confirm", action="store_true", help="确认写入配置；默认只预览")
    setter.add_argument("--json", action="store_true", help="输出 JSON 对象")
    redaction_init = actions.add_parser('init-redaction', help='预览或创建缺失的本地脱敏规则模板')
    redaction_init.add_argument('--confirm', action='store_true', help='确认创建；默认只预览')
    redaction_init.add_argument('--json', action='store_true', help='输出 JSON 对象')
    setter = actions.add_parser('set-capture', help='预览或写入会话结束采集配置')
    setter.add_argument('--enabled', required=True, choices=('true', 'false'), help='是否开启采集')
    setter.add_argument('--min-user-messages', type=int, metavar='N', help='用户消息阈值，必须为正整数')
    setter.add_argument('--ignore-dir', nargs='*', action='extend', default=None, metavar='路径',
                        help='排除目录前缀；不传保留原值，仅传选项清空列表')
    setter.add_argument('--confirm', action='store_true', help='确认写入配置；默认只预览')
    setter.add_argument('--json', action='store_true', help='输出 JSON 对象')
    collector = commands.add_parser('capture', help='会话结束静默采集与状态查询')
    actions = collector.add_subparsers(dest='action', required=True, metavar='采集命令')
    actions.add_parser('hook', help='从标准输入读取 SessionEnd，静默记录候选指针')
    status = actions.add_parser('status', help='只读查看采集配置、队列数量和最近日志')
    status.add_argument('--json', action='store_true', help='输出 JSON 对象')
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
    for operation, label in (('save', '保存'), ('compile', '编译')):
        publisher = commands.add_parser(operation, help='校验草稿、预览并确认后' + label + '知识')
        actions = publisher.add_subparsers(dest='action', required=True, metavar=label + '命令')
        preview = actions.add_parser('preview', help='校验草稿并生成预览指纹')
        preview.add_argument('draft', metavar='草稿目录', help='镜像知识库相对路径的草稿目录')
        preview.add_argument('--json', action='store_true', help='输出 JSON 对象')
        apply = actions.add_parser('apply', help='重新校验指纹后写入并本地提交')
        apply.add_argument('draft', metavar='草稿目录', help='已经预览并确认的草稿目录')
        apply.add_argument('--confirm', required=True, metavar='指纹', help='用户确认的预览指纹')
        apply.add_argument('--json', action='store_true', help='输出 JSON 对象')
    pending = commands.add_parser('commit-pending', help='核对待提交文件与全部契约后完成本地提交')
    pending.add_argument('--json', action='store_true', help='输出 JSON 对象')
    asker = commands.add_parser('ask', help='只读检索知识库')
    actions = asker.add_subparsers(dest='action', required=True, metavar='检索命令')
    searcher = actions.add_parser('search', help='按多个词任意匹配知识页面')
    searcher.add_argument('terms', nargs='+', metavar='词', help='不区分大小写的字面检索词')
    searcher.add_argument('--limit', type=int, default=10, metavar='N', help='最多返回页数，必须为正整数，默认 10')
    searcher.add_argument('--json', action='store_true', help='输出 schema 1 JSON 对象')
    linter = commands.add_parser('lint', help='只读体检知识库并预览安全修复')
    linter.add_argument('--json', action='store_true', help='输出 JSON 对象')
    linter.add_argument('--stale-days', type=int, default=180, metavar='N', help='疑似过期阈值，必须为正整数，默认 180 天')
    actions = linter.add_subparsers(dest='action', metavar='体检命令')
    packer = actions.add_parser('semantic-pack', help='只读提取语义体检候选，默认输出 JSON')
    packer.add_argument('--json', action='store_true', help='输出 JSON 对象（默认）')
    packer.add_argument('--today', metavar='YYYY-MM-DD', help='测试用的今天日期；默认本地日期')
    verifier = actions.add_parser('semantic-verify', help='核对语义报告引文，只输出报告')
    verifier.add_argument('path', metavar='文件|-', help='findings JSON 文件路径，或 - 从标准输入读取')
    verifier.add_argument('--json', action='store_true', help='输出 accepted 与 rejected JSON 对象')
    fixer = actions.add_parser('fix', help='预览或确认执行三类安全修复')
    repairs = fixer.add_subparsers(dest='fix_action', required=True, metavar='修复命令')
    preview = repairs.add_parser('preview', help='生成安全修复预览与指纹')
    preview.add_argument('--json', action='store_true', help='输出 JSON 对象')
    apply = repairs.add_parser('apply', help='确认指纹后写入并本地提交')
    apply.add_argument('--confirm', required=True, metavar='指纹', help='用户确认的预览指纹')
    apply.add_argument('--json', action='store_true', help='输出 JSON 对象')
    queue = commands.add_parser('candidates', help='管理候选会话与查看待编译清单')
    actions = queue.add_subparsers(dest='action', required=True, metavar='候选命令')
    adder = actions.add_parser('add', help='记录候选会话指针，同一会话只保留一条')
    for flag, label in (('session-id', '会话 ID'), ('transcript', '会话记录路径'),
                        ('cwd', '项目目录'), ('reason', '候选原因')):
        adder.add_argument('--' + flag, required=True, help=label)
    listing = actions.add_parser('list', help='列出 inbox 积压与待处理候选')
    listing.add_argument('--json', action='store_true', help='输出 JSON 对象')
    scanner = actions.add_parser('scan-delegate', help='只读扫描 delegate 结果并保存本机候选快照')
    scanner.add_argument('--json', action='store_true', help='输出 JSON 对象，不输出答复内容')
    shower = actions.add_parser('show', help='提取并打码会话文本')
    shower.add_argument('id', metavar='候选ID', help='候选短哈希')
    shower.add_argument('--max-chars', type=int, default=40000, metavar='N', help='最多保留的末尾字数，默认 40000')
    marker = actions.add_parser('mark', help='将候选标为已编译或丢弃')
    marker.add_argument('id', metavar='候选ID', help='候选短哈希')
    marker.add_argument('--status', required=True, choices=('compiled', 'dropped'), help='目标状态')
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


def semantic_report(args):
    if args.action == 'semantic-pack':
        day = today()
        if args.today is not None:
            try:
                day = date.fromisoformat(args.today)
                if day.isoformat() != args.today:
                    raise ValueError
            except ValueError:
                raise KbError('语义体检用法错误：--today 必须是有效的 YYYY-MM-DD 日期') from None
        return semantic.pack(Vault.load(), day)
    try:
        text = sys.stdin.read() if args.path == '-' else Path(args.path).read_text(encoding='utf-8')
    except (OSError, UnicodeError, ValueError):
        raise KbError('无法读取语义体检 findings，需要 UTF-8 JSON 文件或标准输入') from None
    def invalid_constant(value):
        raise ValueError('JSON 不支持非有限数值')

    try:
        findings = json.loads(text, parse_constant=invalid_constant)
        return semantic.verify(Vault.load(), findings)
    except (ValueError, RecursionError):
        raise KbError('语义体检 findings JSON 格式错误') from None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:2] == ['capture', 'hook']:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                build_parser().parse_args(argv)
                capture.run_hook(sys.stdin.read(), os.environ)
            except BaseException as error:
                capture.log_error('采集入口失败：' + type(error).__name__, os.environ)
        return 0
    command = argv[0] if argv else None
    is_doctor = command == "doctor"
    redacted_text = None
    blocklist = []
    try:
        args = build_parser().parse_args(argv)
        if args.command in ('check', 'redact', 'save', 'compile', 'lint', 'commit-pending', 'candidates'):
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
        elif args.command == 'candidates':
            if args.action == 'add':
                result = candidates.add(args.session_id, args.transcript, args.cwd, args.reason)
            elif args.action == 'list':
                result = candidates.list_candidates()
            elif args.action == 'show':
                result = candidates.show(args.id, args.max_chars)
            elif args.action == 'scan-delegate':
                result = delegate_lessons.scan()
            else:
                result = candidates.mark(args.id, args.status)
        elif args.command in ('save', 'compile'):
            publish = save if args.command == 'save' else compile_draft
            result, exit_code = publish(args.draft, args.confirm if args.action == 'apply' else None)
        elif args.command == 'commit-pending':
            result, exit_code = commit_pending()
        elif args.command == 'lint':
            if args.action == 'fix':
                result, exit_code = lint_fix(args.confirm if args.fix_action == 'apply' else None)
            elif args.action in ('semantic-pack', 'semantic-verify'):
                result = semantic_report(args)
            else:
                result = lint_report(Vault.load(), args.stale_days)
        elif args.command == 'ask':
            result = search(Vault.load(), args.terms, args.limit)
        elif args.command == 'capture':
            result = capture.status()
        elif args.command == 'config' and args.action == 'set-capture':
            result = set_capture(args.enabled == 'true', args.min_user_messages, args.ignore_dir, args.confirm)
        elif args.command == 'config' and args.action == 'init-redaction':
            result = init_redaction(args.confirm)
        else:
            result = set_vault(args.path, args.confirm)
        if args.command not in ('save', 'compile', 'commit-pending') and not (args.command == 'lint' and args.action == 'fix'):
            exit_code = (0 if result['pages'] else 1) if args.command == 'ask' else (0 if result["ok"] else 1)
    except KbError as error:
        message = mask_text(str(error), blocklist) if command in ('check', 'redact', 'save', 'compile', 'lint', 'commit-pending', 'candidates') else str(error)
        if command == 'lint' and message.startswith('命令或参数无效。用法：'):
            message = ('体检用法错误。用法：kb.py lint [--json] [--stale-days N]；'
                       'kb.py lint fix preview [--json]；'
                       'kb.py lint fix apply --confirm <指纹> [--json]；'
                       'kb.py lint semantic-pack [--json] [--today YYYY-MM-DD]；'
                       'kb.py lint semantic-verify <文件|-> [--json]。运行 --help 查看帮助。')
        result = {"ok": False, "config": str(config_path()), "error": message}
        if command == 'commit-pending':
            result = empty_pending_result()
            result['error'] = message
        elif command in ('save', 'compile'):
            result = empty_save_result(len(argv) > 1 and argv[1] == 'apply')
            result['findings'] = [{'code': 'config' if '用法' not in message else 'usage',
                                   'path': '.', 'line': 1, 'message': message}]
        elif command == 'lint':
            result.update(groups=[], hints=[], metrics={}, fixable=0)
        elif command in ('check', 'redact'):
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
        elif argv[:2] == ['config', 'init-redaction']:
            result.update(create=[], skip=[], written=False)
        else:
            result.update(content=None, written=False)
        exit_code = error.exit_code
    if "--json" in argv or argv[:2] == ['lint', 'semantic-pack']:
        print(json.dumps(result, ensure_ascii=False))
    elif command == 'candidates':
        if result['ok']:
            if args.action == 'scan-delegate':
                delegate_lessons.print_result(result, blocklist)
            else:
                candidates.print_result(result, args.action, blocklist)
        else:
            print(result['error'], file=sys.stderr)
    elif command == 'commit-pending':
        for finding in result['findings']:
            print(f"{finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
        if result['ok']:
            print(f"待提交文件已本地提交：{result['commit']}")
        else:
            print(result['error'], file=sys.stderr)
    elif command in ('save', 'compile'):
        label = '保存' if command == 'save' else '编译'
        for finding in result['findings']:
            print(f"{finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
        if result['ok']:
            for key, change_label in (('created', '新建'), ('modified', '修改')):
                for path in result[key]:
                    print(f'{change_label}：{path}')
            if 'commit' in result:
                print(f"{label}成功，已本地提交：{result['commit']}")
            else:
                print(f"已替换 {result['replaced_aliases']} 处项目代号。")
                print(result['diff'], end='')
                print(f"预览指纹：{result['fingerprint']}\n校验通过；确认后运行 {command} apply <草稿目录> --confirm {result['fingerprint']}。")
        else:
            print(label + '失败，未完成' + label + '。')
    elif exit_code == 2:
        print(result["error"], file=sys.stderr)
    elif command == 'lint':
        if args.action == 'fix':
            print_lint_fix(result)
        elif args.action == 'semantic-verify':
            semantic.print_report(result)
        else:
            print_lint_report(result)
    elif command == 'capture':
        capture.print_status(result)
    elif command == 'ask':
        zones = {'current': '现行', 'outdated': '过时', 'disputed': '争议'}
        statuses = {'current': '现行', 'superseded': '已被取代'}
        for page in result['pages']:
            print(f"{page['title']}\n路径：{page['path']}\n"
                  f"状态：{statuses.get(page['status'], page['status'])}；得分：{page['score']}")
            if page['superseded_by']:
                print(f"取代页面：{page['superseded_by']}")
            for hit in page['hits']:
                print(f"  第 {hit['line']} 行 [{zones[hit['zone']]}] {hit['text']}")
        if not result['pages']:
            print('知识库里没有命中页面。')
        if result['truncated']:
            print('结果已截断，可增大 --limit 查看更多页面。')
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
            label = '提醒' if check.get('level') == 'warn' else ('通过' if check['ok'] else '失败')
            print(f"{label}：{check['message']}")
        print("自检通过。" if result["ok"] else result["error"])
    elif argv[:2] == ['config', 'init-redaction']:
        print(f"{'已初始化脱敏配置' if result['written'] else '脱敏配置预览'}：{Path(result['config']).parent}")
        for name in result['create']:
            print(f"{'已创建' if result['written'] else '将创建'}：{name}")
        for name in result['skip']:
            print(f'跳过（已存在，不读取、不覆盖）：{name}')
        print('规则内容由用户自己填写；aliases.json 格式：{"真实名称": "proj-xxx"}。')
        print('新模板没有任何规则；本地脱敏规则文件不要放进任何仓库。')
        if not result['written']:
            print('尚未写入文件；确认后在同一命令后追加 --confirm。')
    else:
        print(f"{'已写入配置' if result['written'] else '预览，将写入配置'}：{result['config']}")
        print(json.dumps(result["content"], ensure_ascii=False, indent=2))
        if not result["written"]:
            print("尚未写入文件；确认后在同一命令后追加 --confirm。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
