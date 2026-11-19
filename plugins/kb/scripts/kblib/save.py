"""Validate save drafts in an isolated repository before publishing them."""

from dataclasses import asdict, replace
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from . import KbError, checks
from .config import config_path, load_aliases, load_blocklist, read_optional_text, resolve_vault
from .markdown import parse_frontmatter
from .redaction import apply_aliases, mask_text, parse_allowlist, scan
from .vault import Vault, git, is_git_repository


class SaveError(KbError):
    exit_code = 1

    def __init__(self, message, code='save', path='.', exit_code=1):
        super().__init__(message)
        self.code = code
        self.path = path
        self.exit_code = exit_code


def empty_result(apply=False):
    result = {'ok': False, 'created': [], 'modified': [], 'findings': []}
    if apply:
        result['commit'] = None
    else:
        result.update(fingerprint=None, diff='', replaced_aliases=0)
    return result


def _state(root):
    if not is_git_repository(root):
        raise KbError('知识库必须是独立的 git 仓库，请先运行 kb.py init')
    head = git(root, 'rev-parse', '--verify', 'HEAD')
    if head.returncode:
        raise KbError('知识库尚无 HEAD 提交，请先提交初始化骨架')
    status = git(root, 'status', '--porcelain=v1', '-z')
    if status.returncode:
        raise SaveError('无法读取知识库 git 状态')
    return head.stdout.strip(), status.stdout


def _target(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise SaveError('草稿路径必须是知识库相对路径，禁止 .. 路径', 'path', relative)
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise SaveError('知识库目标路径禁止符号链接', 'path', relative)
    if not target.resolve().is_relative_to(root):
        raise SaveError('草稿目标路径超出知识库范围', 'path', relative)
    return target


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
            target = _target(root, relative)
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


def _fingerprint(state, originals, content):
    digest = hashlib.sha256()
    parts = list(state)
    for path in sorted(content):
        parts.extend((path.encode('utf-8'), hashlib.sha256(originals[path]).digest(),
                      content[path].encode('utf-8')))
    for part in parts:
        digest.update(len(part).to_bytes(8, 'big'))
        digest.update(part)
    return digest.hexdigest()[:16]


def _overlay_check(root, content, original_config):
    with tempfile.TemporaryDirectory(prefix='kb-save-check-') as temporary:
        base = Path(temporary).resolve()
        overlay = base / 'vault'
        # A file URL is unnecessary: this is always a local path, never a remote.
        cloned = git(root, 'clone', '--no-hardlinks', '--', str(root), str(overlay))
        if cloned.returncode:
            raise SaveError('无法创建保留完整 git 历史的知识库临时副本')
        # Synchronize the actual worktree, including ignored files and deletions,
        # while keeping the clone's independent object database and history.
        for child in overlay.iterdir():
            if child.name != '.git':
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        shutil.copytree(root, overlay, dirs_exist_ok=True, symlinks=True,
                        ignore=lambda directory, names: ['.git'] if Path(directory) == root else [])
        for relative, text in content.items():
            target = _target(overlay, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode('utf-8'))
        config = base / 'config.json'
        config.write_text(json.dumps({'version': 1, 'vault': str(overlay)}), encoding='utf-8')
        snapshot = Vault.load(environ={'KB_CONFIG': str(config)})
        # Checks resolve blocklist.txt beside config_file. Keep the real location
        # without writing temporary files into the user's configuration directory.
        return checks.check(replace(snapshot, config_file=original_config))


def _diff(root, content):
    created, modified, changes = [], [], []
    for relative, text in sorted(content.items()):
        target = _target(root, relative)
        before = target.read_bytes() if target.exists() else None
        if before == text.encode('utf-8'):
            continue
        (created if before is None else modified).append(relative)
        old_text = before.decode('utf-8') if before is not None else ''
        for line in difflib.unified_diff(old_text.splitlines(keepends=True),
                                        text.splitlines(keepends=True),
                                        fromfile=relative if before is not None else '/dev/null',
                                        tofile=relative):
            changes.append(line if line.endswith('\n') else
                           line + '\n\\ No newline at end of file\n')
    return created, modified, ''.join(changes)


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


def _atomic_write(root, content):
    staged, backups, written, directories = {}, {}, [], []

    def temporary(target, data, mode=None):
        descriptor, name = tempfile.mkstemp(prefix='.kb-save-', dir=str(target.parent))
        path = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if mode is not None:
                path.chmod(mode)
            return path
        except OSError:
            path.unlink(missing_ok=True)
            raise

    rollback_failed = False
    try:
        for relative, text in sorted(content.items()):
            target = _target(root, relative)
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir()
                directories.append(parent)
            mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
            if target.exists():
                backups[relative] = temporary(target, target.read_bytes(), mode)
            staged[relative] = temporary(target, text.encode('utf-8'), mode)
        for relative, path in staged.items():
            os.replace(path, _target(root, relative))
            written.append(relative)
    except (OSError, SaveError):
        for relative in reversed(written):
            try:
                if relative in backups:
                    os.replace(backups[relative], root / relative)
                else:
                    (root / relative).unlink()
            except OSError:
                rollback_failed = True
        if rollback_failed:
            raise SaveError('写入失败且回滚未能完成，已保留 .kb-save- 备份，请人工恢复') from None
        raise SaveError('写入失败，已完整回滚本次文件改动') from None
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
        if not rollback_failed:
            for path in backups.values():
                path.unlink(missing_ok=True)
        for directory in reversed(directories):
            try:
                directory.rmdir()
            except OSError:
                pass


def _commit(root, paths, title):
    added = git(root, '--literal-pathspecs', 'add', '--', *paths)
    if added.returncode:
        reason = added.stderr.decode('utf-8', errors='replace').strip()
        raise SaveError('git add 失败；已保留写入文件，请处理后手动提交：' + reason)
    committed = git(root, '--literal-pathspecs', 'commit', '-m', 'save: ' + title,
                    '--only', '--', *paths)
    if committed.returncode:
        reason = (committed.stderr + committed.stdout).decode('utf-8', errors='replace').strip()
        raise SaveError('git 提交失败；已保留写入文件与暂存状态，不执行 reset：' + reason)
    head = git(root, 'rev-parse', 'HEAD')
    if head.returncode:
        raise SaveError('提交已执行，但无法读取提交号；请检查 git log，已保留写入文件')
    return head.stdout.decode('ascii').strip()


def save(draft, confirm=None):
    applying = confirm is not None
    result = empty_result(applying)
    blocklist = load_blocklist()
    aliases = load_aliases()
    root = resolve_vault().resolve()
    try:
        state = _state(root)
        originals, content, count = _read_draft(draft, root, aliases)
        fingerprint = _fingerprint(state, originals, content)
        if applying and fingerprint != confirm:
            raise SaveError('预览指纹不匹配，知识库或草稿已变化；请重新 preview',
                            'fingerprint', exit_code=3)
        if state[1]:
            raise SaveError('知识库有未提交改动，请先处理未提交改动后再 save', 'worktree')
        allow_entries, errors = parse_allowlist(read_optional_text(root / 'redaction-allow.txt'))
        findings = [checks.Finding('redaction', f.path, f.line, f.masked) for f in errors]
        for path, text in sorted(content.items()):
            findings.extend(checks.Finding('redaction', f.path, f.line,
                            f'{f.category}：{f.masked}（第 {f.column} 列）')
                            for f in scan(text, path, blocklist, allow_entries))
        if not applying:
            result['replaced_aliases'] = count
        findings = list(dict.fromkeys(findings + _overlay_check(root, content, config_path())))
        result['findings'] = [asdict(f) for f in findings]
        if findings:
            return _masked(result, blocklist), 1
        if _state(root) != state:
            raise SaveError('校验期间知识库已变化，请重新 preview', 'fingerprint', exit_code=3)
        created, modified, diff = _diff(root, content)
        result.update(ok=True, created=created, modified=modified)
        if applying:
            paths = sorted(created + modified)
            title = _title(content, paths)
            _atomic_write(root, {path: content[path] for path in paths})
            result['commit'] = _commit(root, paths, title)
        else:
            result.update(fingerprint=fingerprint, diff=diff)
        return _masked(result, blocklist), 0
    except SaveError as error:
        result['ok'] = False
        result['findings'] = [{'code': error.code, 'path': error.path, 'line': 1, 'message': str(error)}]
        return _masked(result, blocklist), error.exit_code
    except (OSError, UnicodeError, ValueError, RuntimeError):
        result['ok'] = False
        result['findings'] = [{'code': 'save', 'path': '.', 'line': 1,
                               'message': '无法读取草稿或校验知识库，请检查文件、权限与 git 状态'}]
        return _masked(result, blocklist), 1


def _masked(result, blocklist):
    # Diff may include old content; diagnostics and filenames share redact's rules.
    result['findings'] = [{**f, 'path': mask_text(f['path'], blocklist),
                           'message': mask_text(f['message'], blocklist)} for f in result['findings']]
    for key in ('created', 'modified'):
        result[key] = [mask_text(path, blocklist) for path in result[key]]
    if 'diff' in result:
        result['diff'] = mask_text(result['diff'], blocklist)
    return result
