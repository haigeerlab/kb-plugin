"""Read-only vault snapshots, directory names, and local dates."""

from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
from typing import Optional

from . import KbError
from .config import resolve_vault
from .markdown import parse_frontmatter


TYPE_DIRS = {
    'pitfall': 'pitfalls', 'decision': 'decisions', 'tech': 'tech',
    'pattern': 'patterns', 'project': 'projects',
}
REQUIRED_SECTIONS = {
    'pitfall': ('症状', '原因', '解法', '适用范围', '如何验证'),
    'decision': ('背景', '选项', '决定', '理由', '后果'),
    'tech': ('原理', '用法', '坑', '搭配', '最佳实践'),
    'pattern': ('问题', '方案', '适用条件', '反例'),
    'project': ('概况', '相关坑', '相关决策'),
}
DIRECTORIES = ('inbox', 'raw', 'wiki', *(f'wiki/{name}' for name in TYPE_DIRS.values()), 'templates')
SCHEMA_VERSION = 1


def today():
    return datetime.now().astimezone().date()


def git(root, *args):
    return subprocess.run(
        ['git', '-C', str(root), *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'),
    )


def is_git_repository(root):
    """An ancestor repository does not make this directory a vault repository."""
    result = git(root, 'rev-parse', '--show-toplevel')
    return result.returncode == 0 and Path(os.fsdecode(result.stdout).strip()).resolve() == root.resolve()


@dataclass(frozen=True)
class Document:
    path: str
    text: str

    @property
    def frontmatter(self):
        return parse_frontmatter(self.text)


@dataclass(frozen=True)
class Vault:
    root: Path
    documents: dict
    files: frozenset
    read_errors: dict
    selected: Optional[frozenset]
    date: date
    immutable_paths: tuple
    git_error: Optional[str]

    @classmethod
    def load(cls, paths=(), environ=None):
        root = (resolve_vault() if environ is None else resolve_vault(environ)).resolve()
        selected = set() if paths else None
        for value in paths:
            path = Path(value)
            target = (path if path.is_absolute() else root / path).resolve()
            try:
                relative = target.relative_to(root).as_posix()
            except ValueError:
                raise KbError(f'检查路径必须位于知识库内：{value}') from None
            if not target.exists() or not (target.is_file() or target.is_dir()):
                raise KbError(f'检查路径不存在或不是普通文件、目录：{value}')
            if target.is_dir():
                selected.update(p.relative_to(root).as_posix() for p in target.rglob('*') if p.is_file() and p.suffix.lower() == '.md')
            elif target.suffix.lower() != '.md':
                raise KbError(f'检查路径必须是 Markdown 文件：{value}')
            else:
                selected.add(relative)
        documents, files, errors = {}, set(), {}
        try:
            for directory, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d != '.git')
                for name in sorted(names):
                    path = Path(directory) / name
                    relative = path.relative_to(root).as_posix()
                    if not path.resolve().is_relative_to(root) or not path.is_file():
                        continue
                    files.add(relative)
                    if path.suffix.lower() == '.md' or relative.startswith(('inbox/', 'raw/')):
                        try:
                            documents[relative] = Document(relative, path.read_text(encoding='utf-8'))
                        except (OSError, UnicodeError):
                            errors[relative] = '无法读取文件，需要 UTF-8 文本'
        except OSError:
            raise KbError(f'无法读取知识库目录：{root}') from None
        changes, error = (), None
        try:
            if not is_git_repository(root):
                error = '知识库必须是独立的 git 仓库；请运行 kb.py init 预览，确认后加 --confirm 执行 git init'
            elif git(root, 'rev-parse', '--verify', 'HEAD').returncode == 0:
                result = git(root, 'diff', '--name-only', '-z', '--no-renames', '--diff-filter=MDTUXB',
                             'HEAD', '--', 'inbox/', 'raw/')
                # Source files may only ever be added: also catch modifications or deletions that were
                # already committed (e.g. by a faulty save), not just uncommitted ones.
                history = git(root, 'log', '--format=', '--name-only', '-z', '--no-renames',
                              '--diff-filter=MDTUXB', 'HEAD', '--', 'inbox/', 'raw/')
                if result.returncode or history.returncode:
                    error = '无法比较已提交的原文，请检查知识库 git 状态'
                else:
                    paths = result.stdout.split(b'\0') + history.stdout.replace(b'\n', b'\0').split(b'\0')
                    changes = tuple(sorted({os.fsdecode(p) for p in paths if p}))
        except OSError:
            error = '无法运行 git；请安装 git 后运行 kb.py init 初始化知识库'
        return cls(root, documents, frozenset(files), errors,
                   frozenset(selected) if selected is not None else None, today(), changes, error)

    def pages(self):
        return [doc for path, doc in sorted(self.documents.items())
                if path.startswith('wiki/') and path.lower().endswith('.md')
                and (self.selected is None or path in self.selected)]

    def entries(self):
        return [doc for path, doc in sorted(self.documents.items())
                if path.startswith('inbox/')
                and (self.selected is None or path in self.selected)]
