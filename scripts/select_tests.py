#!/usr/bin/env python3
"""validate.sh --quick 用：按本分支改动挑出要跑的测试文件（插件开发规范 C2）。

输出到 stdout：
  ALL            改动对应不上测试（或无法判断改动），调用方应跑全量
  test_a test_b  只需跑这些测试模块（空行表示改动不涉及任何测试）
原因写到 stderr。只看本仓库的 git 状态，不读任何 kb 知识库。保持 Python 3.9 兼容。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KBLIB = 'plugins/kb/scripts/kblib/'
TESTS = ROOT / 'tests'

# 不进单元测试的文件：改它们不需要跑测试（清单与本机路径检查仍会跑）。
NO_TEST = re.compile(r'^(?:[^/]+\.md|LICENSE|spec/.*|docs/.*|tasks/.*|\.github/.*|\.agent/.*|\.gitignore)$')
# 脚本到测试的固定对应。
SCRIPT_TESTS = {
    'scripts/check_local_paths.py': ['test_local_paths'],
    'scripts/check-manifests.py': ['test_manifests'],
    'scripts/select_tests.py': ['test_select_tests'],
}
# kblib 模块名和测试文件名不同的对应。没有专门测试的模块（config、writer、checks 等）一律退回全量。
MODULE_TESTS = {
    'vault': ['test_vault_contract', 'test_vault_cli'],
}
IMPORT_RE = re.compile(r'^from \.(\w*) import ([\w, ]+)', re.M)


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(' '.join(args))
    return [line for line in result.stdout.splitlines() if line]


def changed_files():
    base = git('merge-base', 'HEAD', 'origin/main')[0]
    files = set(git('diff', '--name-only', base))
    files.update(git('ls-files', '--others', '--exclude-standard'))
    return sorted(files)


def reverse_deps():
    """kblib 模块 -> 直接导入它的 kblib 模块。"""
    users = {}
    for path in (ROOT / KBLIB).glob('*.py'):
        for target, names in IMPORT_RE.findall(path.read_text(encoding='utf-8')):
            deps = [target] if target else [n.strip() for n in names.split(',')]
            for dep in deps:
                users.setdefault(dep, set()).add(path.stem)
    return users


def tests_for_module(name):
    if name in MODULE_TESTS:
        return MODULE_TESTS[name]
    if (TESTS / ('test_%s.py' % name)).exists():
        return ['test_%s' % name]
    return None


def select(files):
    users = reverse_deps()
    selected = set()
    for f in files:
        if NO_TEST.match(f):
            continue
        if f.startswith('tests/test_') and f.endswith('.py') and '/' not in f[len('tests/'):]:
            if (ROOT / f).exists():
                selected.add(Path(f).stem)
            continue
        if f in SCRIPT_TESTS:
            selected.update(SCRIPT_TESTS[f])
            continue
        if f.startswith(KBLIB) and f.endswith('.py') and '/' not in f[len(KBLIB):]:
            pending, seen = [Path(f).stem], set()
            while pending:
                mod = pending.pop()
                if mod in seen:
                    continue
                seen.add(mod)
                tests = tests_for_module(mod)
                if tests is None:
                    return None, '%s 影响的模块 %s 没有专门的测试' % (f, mod)
                selected.update(tests)
                pending.extend(users.get(mod, ()))
            # kblib 都经 kb.py 暴露，命令行与端到端验收也要跑。
            selected.update(['test_cli', 'test_acceptance'])
            continue
        return None, '%s 对应不上测试' % f
    return sorted(selected), '%d 个改动文件' % len(files)


def main():
    try:
        files = changed_files()
    except (RuntimeError, IndexError):
        print('无法和 origin/main 比较改动，退回全量', file=sys.stderr)
        print('ALL')
        return 0
    tests, reason = select(files)
    if tests is None:
        print('%s，退回全量' % reason, file=sys.stderr)
        print('ALL')
    else:
        print('%s，选中 %d 个测试文件' % (reason, len(tests)), file=sys.stderr)
        print(' '.join(tests))
    return 0


if __name__ == '__main__':
    sys.exit(main())
