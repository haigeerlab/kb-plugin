"""Shared validation, preview fingerprints and atomic vault publishing."""

from dataclasses import asdict, replace
from datetime import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import tempfile

from . import KbError, checks
from .config import load_blocklist, read_optional_text, resolve_vault
from .redaction import mask_text, parse_allowlist, scan
from .vault import PENDING_FILE, Vault, git, is_git_repository


class WriteError(KbError):
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


def pending_command():
    entry = shlex.quote(str(Path(__file__).resolve().parents[1] / 'kb.py'))
    return 'python3 -B ' + entry + ' commit-pending'


def reject_pending(root):
    pending = root / PENDING_FILE
    if pending.exists() or pending.is_symlink():
        raise WriteError('知识库有待提交记录，请先运行：' + pending_command(), 'pending')


def state(root):
    if not is_git_repository(root):
        raise KbError('知识库必须是独立的 git 仓库，请先运行 kb.py init')
    head = git(root, 'rev-parse', '--verify', 'HEAD')
    if head.returncode:
        raise KbError('知识库尚无 HEAD 提交，请先提交初始化骨架')
    status = git(root, 'status', '--porcelain=v1', '-z')
    if status.returncode:
        raise WriteError('无法读取知识库 git 状态')
    return head.stdout.strip(), status.stdout


def target_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise WriteError('草稿路径必须是知识库相对路径，禁止 .. 路径', 'path', relative)
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise WriteError('知识库目标路径禁止符号链接', 'path', relative)
    if not target.resolve().is_relative_to(root):
        raise WriteError('草稿目标路径超出知识库范围', 'path', relative)
    return target


def fingerprint(state, originals, content):
    digest = hashlib.sha256()
    parts = list(state)
    for path in sorted(content):
        parts.extend((path.encode('utf-8'), hashlib.sha256(originals[path]).digest(),
                      content[path].encode('utf-8')))
    for part in parts:
        digest.update(len(part).to_bytes(8, 'big'))
        digest.update(part)
    return digest.hexdigest()[:16]


def overlay_check(root, content, original_config):
    with tempfile.TemporaryDirectory(prefix='kb-save-check-') as temporary:
        base = Path(temporary).resolve()
        overlay = base / 'vault'
        # A file URL is unnecessary: this is always a local path, never a remote.
        cloned = git(root, 'clone', '--no-hardlinks', '--', str(root), str(overlay))
        if cloned.returncode:
            raise WriteError('无法创建保留完整 git 历史的知识库临时副本')
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
            target = target_path(overlay, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode('utf-8'))
        config = base / 'config.json'
        config.write_text(json.dumps({'version': 1, 'vault': str(overlay)}), encoding='utf-8')
        snapshot = Vault.load(environ={'KB_CONFIG': str(config)})
        # Checks resolve blocklist.txt beside config_file. Keep the real location
        # without writing temporary files into the user's configuration directory.
        return checks.check(replace(snapshot, config_file=original_config))


def diff(root, content):
    created, modified, changes = [], [], []
    for relative, text in sorted(content.items()):
        target = target_path(root, relative)
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


def atomic_write(root, content):
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
            target = target_path(root, relative)
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
            os.replace(path, target_path(root, relative))
            written.append(relative)
    except (OSError, WriteError):
        for relative in reversed(written):
            try:
                if relative in backups:
                    os.replace(backups[relative], root / relative)
                else:
                    (root / relative).unlink()
            except OSError:
                rollback_failed = True
        if rollback_failed:
            raise WriteError('写入失败且回滚未能完成，已保留 .kb-save- 备份，请人工恢复') from None
        raise WriteError('写入失败，已完整回滚本次文件改动') from None
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


def commit(root, paths, message):
    added = git(root, '--literal-pathspecs', 'add', '--', *paths)
    if added.returncode:
        reason = added.stderr.decode('utf-8', errors='replace').strip()
        raise WriteError('git add 失败；已保留写入文件，请处理后手动提交：' + reason)
    committed = git(root, '--literal-pathspecs', 'commit', '-m', message,
                    '--only', '--', *paths)
    if committed.returncode:
        reason = (committed.stderr + committed.stdout).decode('utf-8', errors='replace').strip()
        raise WriteError('git 提交失败；已保留写入文件与暂存状态，不执行 reset：' + reason)
    head = git(root, 'rev-parse', 'HEAD')
    if head.returncode:
        raise WriteError('提交已执行，但无法读取提交号；请检查 git log，已保留写入文件')
    return head.stdout.decode('ascii').strip()


def empty_pending_result():
    return {'ok': False, 'commit': None, 'files': [], 'findings': [], 'error': None}


def _read_pending(root):
    path = root / PENDING_FILE
    if path.is_symlink():
        raise KbError('待提交记录不能是符号链接')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise KbError('没有待提交记录') from None
    except (OSError, UnicodeError, ValueError):
        raise KbError('无法读取待提交记录：JSON 损坏或文件不可读') from None
    if (not isinstance(record, dict) or type(record.get('schema')) is not int
            or record['schema'] != 1 or record.get('operation') not in ('save', 'lint', 'compile')
            or not isinstance(record.get('message'), str) or not record['message'].strip()
            or '\0' in record['message']
            or not isinstance(record.get('files'), dict) or not record['files']
            or not isinstance(record.get('fingerprint'), str)
            or not re.fullmatch(r'[0-9a-f]{16}', record['fingerprint'])
            or not isinstance(record.get('created'), str)):
        raise KbError('待提交记录格式无效：需要 schema 1 及完整的提交信息、文件哈希与预览信息')
    try:
        datetime.fromisoformat(record['created'])
    except ValueError:
        raise KbError('待提交记录格式无效：created 必须是 ISO 时间') from None
    for relative, digest in record['files'].items():
        path = Path(relative)
        if (not relative or '\0' in relative or path.as_posix() != relative
                or path.is_absolute() or '..' in path.parts or '\\' in relative
                or any(part.lower() == '.git' for part in path.parts)
                or relative == PENDING_FILE or relative == '.'
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise KbError('待提交记录格式无效：文件必须是库内相对路径，并带 SHA-256 哈希')
    return record


def _verify_pending(root, files):
    for relative, expected in files.items():
        target = target_path(root, relative)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise WriteError('待提交文件缺失或内容与记录不一致：' + relative)
    status = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    if status.returncode:
        raise WriteError('无法读取知识库 git 状态')
    entries = iter(status.stdout.split(b'\0'))
    changed = set()
    for entry in entries:
        if not entry:
            continue
        changed.add(os.fsdecode(entry[3:]))
        if b'R' in entry[:2] or b'C' in entry[:2]:
            changed.add(os.fsdecode(next(entries, b'')))
    if changed - set(files) - {PENDING_FILE}:
        raise WriteError('知识库有待提交记录以外的改动（含未跟踪文件），请先处理这些改动')


def commit_pending():
    result = empty_pending_result()
    blocklist = load_blocklist()
    root = resolve_vault().resolve()
    try:
        record = _read_pending(root)
        result['files'] = sorted(record['files'])
        state(root)
        _verify_pending(root, record['files'])
        result['findings'] = [asdict(f) for f in checks.check(Vault.load())]
        if result['findings']:
            raise WriteError('知识库全量检查未通过，请先处理检查问题；待提交记录已保留')
        # Recheck after the full scan so changes made during checks are refused.
        _verify_pending(root, record['files'])
        result['commit'] = commit(root, result['files'], record['message'])
        (root / PENDING_FILE).unlink()
        result['ok'] = True
        exit_code = 0
    except KbError as error:
        result['error'] = mask_text(str(error), blocklist)
        exit_code = error.exit_code
    except (OSError, UnicodeError, ValueError, RuntimeError):
        result['error'] = ('提交已完成，但无法删除待提交记录，请检查文件权限'
                           if result['commit'] else '无法核对或提交待提交文件，请检查文件、权限与 git 状态')
        exit_code = 1
    result['files'] = [mask_text(path, blocklist) for path in result['files']]
    return result, exit_code


def masked(result, blocklist):
    # Diff may include old content; diagnostics and filenames share redact's rules.
    result['findings'] = [{**f, 'path': mask_text(f['path'], blocklist),
                           'message': mask_text(f['message'], blocklist)} for f in result['findings']]
    for key in ('created', 'modified'):
        result[key] = [mask_text(path, blocklist) for path in result[key]]
    if 'diff' in result:
        result['diff'] = mask_text(result['diff'], blocklist)
    return result


def publish(root, initial_state, originals, content, confirm, result, blocklist,
            original_config, commit_message, operation='save', replaced_aliases=0):
    """Validate an overlay, then preview or publish the caller-approved content."""
    reject_pending(root)
    applying = confirm is not None
    token = fingerprint(initial_state, originals, content)
    if applying and token != confirm:
        raise WriteError('预览指纹不匹配，知识库或草稿已变化；请重新 preview',
                         'fingerprint', exit_code=3)
    if initial_state[1]:
        raise WriteError('知识库有未提交改动，请先处理未提交改动后再 ' + operation, 'worktree')
    allow_entries, errors = parse_allowlist(read_optional_text(root / 'redaction-allow.txt'))
    findings = [checks.Finding('redaction', f.path, f.line, f.masked) for f in errors]
    for path, text in sorted(content.items()):
        findings.extend(checks.Finding('redaction', f.path, f.line,
                        f'{f.category}：{f.masked}（第 {f.column} 列）')
                        for f in scan(text, path, blocklist, allow_entries))
    if not applying:
        result['replaced_aliases'] = replaced_aliases
    findings = list(dict.fromkeys(findings + overlay_check(root, content, original_config)))
    result['findings'] = [asdict(f) for f in findings]
    if findings:
        return masked(result, blocklist), 1
    if state(root) != initial_state:
        raise WriteError('校验期间知识库已变化，请重新 preview', 'fingerprint', exit_code=3)
    created, modified, changes = diff(root, content)
    result.update(ok=True, created=created, modified=modified)
    if applying:
        paths = sorted(created + modified)
        message = commit_message(content, paths)
        atomic_write(root, {path: content[path] for path in paths})
        try:
            result['commit'] = commit(root, paths, message)
        except (WriteError, OSError) as error:
            record = {'schema': 1, 'operation': 'lint' if operation == 'lint fix' else operation,
                      'message': message,
                      'files': {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                                for path in paths},
                      'fingerprint': token, 'created': datetime.now().astimezone().isoformat()}
            try:
                atomic_write(root, {PENDING_FILE: json.dumps(record, ensure_ascii=False, indent=2) + '\n'})
            except (WriteError, OSError):
                raise error
            reason = mask_text(str(error), blocklist)
            raise WriteError('文件已写入但提交失败（原因：' + reason + '，已打码）；'
                             '已保留写入文件与暂存状态；已记录待提交，请在可写 .git 的环境运行：'
                             + pending_command()) from None
    else:
        result.update(fingerprint=token, diff=changes)
    return masked(result, blocklist), 0

