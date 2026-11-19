"""Validate save drafts in an isolated repository before publishing them."""

# Keep the os module available for callers injecting filesystem failures.
import os
from pathlib import Path
import stat

from . import KbError, writer
from .config import config_path, load_aliases, load_blocklist, resolve_vault
from .markdown import parse_frontmatter
from .redaction import apply_aliases
from .writer import WriteError as SaveError, empty_result


def _read_draft(value, root, aliases):
    draft = Path(value).expanduser()
    if '..' in draft.parts:
        raise SaveError('草稿目录禁止包含 .. 路径', 'path')
    if draft.is_symlink():
        raise SaveError('草稿目录禁止符号链接', 'path')
    if not draft.is_dir():
        raise KbError('草稿目录必须是存在的普通目录')
    draft = draft.resolve()
    if draft.is_relative_to(root) or root.is_relative_to(draft):
        raise SaveError('草稿目录必须与知识库目录分开，禁止相互包含', 'path')
    originals, content, count = {}, {}, 0

    def visit(directory):
        nonlocal count
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(draft).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise SaveError('草稿禁止符号链接，不能指向知识库之外', 'path', relative)
            target = writer.target_path(root, relative)
            if stat.S_ISDIR(mode):
                if relative not in ('inbox', 'wiki') and not relative.startswith(('inbox/', 'wiki/')):
                    raise SaveError('草稿目录不在路径白名单内，不支持删除', 'path', relative)
                if target.exists() and not target.is_dir():
                    raise SaveError('草稿目录与知识库已有文件冲突，不支持删除', 'path', relative)
                visit(path)
                continue
            if not stat.S_ISREG(mode):
                raise SaveError('草稿只支持普通 UTF-8 文本文件，不支持删除', 'path', relative)
            if not (relative.startswith(('inbox/', 'wiki/')) or relative in ('index.md', 'log.md')):
                raise SaveError('草稿文件不在路径白名单内；raw/ 不可写入，不支持删除', 'path', relative)
            if relative.startswith('inbox/') and target.exists():
                raise SaveError('inbox/ 只允许新建文件，禁止修改已有原文', 'path', relative)
            if target.exists() and not target.is_file():
                raise SaveError('草稿文件与知识库已有目录冲突，不支持删除', 'path', relative)
            data = path.read_bytes()
            try:
                text = data.decode('utf-8')
            except UnicodeError:
                raise SaveError('草稿必须是 UTF-8 文本文件', 'path', relative) from None
            text, replaced = apply_aliases(text, aliases)
            originals[relative], content[relative] = data, text
            count += replaced

    visit(draft)
    if sum(path.startswith('inbox/') for path in content) != 1:
        raise SaveError('一次 save 必须恰好包含 1 个 inbox/ 下的新文件', 'path')
    return originals, content, count


def _title(content, changed):
    entry = next(path for path in content if path.startswith('inbox/'))
    pages = [(path, parse_frontmatter(content[path]).data) for path in sorted(changed)
             if path.startswith('wiki/') and path.endswith('.md')]
    main_pages = [data for _, data in pages if entry in data.get('raw', [])
                  and data.get('type') != 'project']
    if not main_pages:
        main_pages = [data for _, data in pages if data.get('type') != 'project']
    if not main_pages:
        main_pages = [data for _, data in pages]
    if main_pages:
        return main_pages[0]['title']
    title = parse_frontmatter(content[entry]).data.get('title')
    return title if isinstance(title, str) and title.strip() else Path(entry).name


def save(draft, confirm=None):
    applying = confirm is not None
    result = empty_result(applying)
    blocklist = load_blocklist()
    aliases = load_aliases()
    root = resolve_vault().resolve()
    try:
        writer.reject_pending(root)
        state = writer.state(root)
        originals, content, count = _read_draft(draft, root, aliases)
        return writer.publish(root, state, originals, content, confirm, result, blocklist,
                              config_path(), lambda text, paths: 'save: ' + _title(text, paths),
                              replaced_aliases=count)
    except SaveError as error:
        result['ok'] = False
        result['findings'] = [{'code': error.code, 'path': error.path, 'line': 1, 'message': str(error)}]
        return writer.masked(result, blocklist), error.exit_code
    except (OSError, UnicodeError, ValueError, RuntimeError):
        result['ok'] = False
        result['findings'] = [{'code': 'save', 'path': '.', 'line': 1,
                               'message': '无法读取草稿或校验知识库，请检查文件、权限与 git 状态'}]
        return writer.masked(result, blocklist), 1
