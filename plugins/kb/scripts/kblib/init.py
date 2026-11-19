"""Preview or create a missing vault skeleton, never replacing content."""

from pathlib import Path

from . import KbError
from .config import resolve_vault
from .vault import DIRECTORIES, git, is_git_repository, today


TEMPLATES = Path(__file__).resolve().parents[2] / 'templates'


def initialize(confirm=False):
    root = resolve_vault().resolve()
    content = {}
    try:
        for path in sorted(TEMPLATES.rglob('*.md')):
            relative = path.relative_to(TEMPLATES)
            destination = ('templates/' + relative.name) if relative.parts[0] == 'pages' else relative.as_posix()
            content[destination] = path.read_text(encoding='utf-8').replace('{{date}}', today().isoformat())
        needs_git = not is_git_repository(root)
        create, skip = [], []
        for relative in (*[d + '/' for d in DIRECTORIES], *content):
            target = root / relative
            if not target.resolve().is_relative_to(root):
                raise KbError(f'初始化路径超出知识库范围：{relative}')
            if relative.endswith('/') and target.exists() and not target.is_dir():
                raise KbError(f'初始化目录被同名文件占用：{relative}，请先处理后重试')
            (skip if target.exists() or target.is_symlink() else create).append(relative)
        if confirm:
            if needs_git and git(root, 'init', '-q').returncode:
                raise KbError('git init 失败，请检查知识库目录权限与 git 配置')
            for directory in DIRECTORIES:
                (root / directory).mkdir(parents=True, exist_ok=True)
            for relative, text in content.items():
                if relative not in create:
                    continue
                try:
                    with (root / relative).open('x', encoding='utf-8') as stream:
                        stream.write(text)
                except FileExistsError:
                    create.remove(relative)
                    skip.append(relative)
    except (OSError, UnicodeError):
        raise KbError('无法初始化知识库，请检查模板、目录与 git 是否可用，以及文件权限') from None
    return {'ok': True, 'vault': str(root), 'create': create, 'skip': skip,
            'git_init': needs_git, 'written': confirm, 'error': None}
