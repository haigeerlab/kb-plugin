"""Local candidate pointers and redacted Claude Code conversation extraction."""

from datetime import datetime, timedelta
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile

from . import KbError
from .config import load_blocklist
from .lint import inbox_backlog
from .redaction import mask_text
from .vault import Vault


STATUSES = ('pending', 'compiled', 'dropped', 'expired')
FIELDS = ('id', 'session_id', 'transcript_path', 'cwd', 'reason', 'ended_at', 'status')


class CandidateError(KbError):
    exit_code = 1


def queue_path(environ=os.environ):
    return Path(environ.get('KB_STATE_DIR') or '~/.local/state/kb').expanduser() / 'candidates.jsonl'


def _read_queue(environ=os.environ):
    try:
        lines = queue_path(environ).read_bytes().splitlines(keepends=True)
    except FileNotFoundError:
        lines = []
    except OSError:
        raise CandidateError('无法读取候选队列，请检查路径与权限') from None
    rows, corrupt = [], []
    for number, raw in enumerate(lines, 1):
        try:
            record = json.loads(raw.decode('utf-8'))
            if (not isinstance(record, dict)
                    or any(not isinstance(record.get(key), str) for key in FIELDS)
                    or not record['session_id'] or record['status'] not in STATUSES
                    or record['id'] != _identifier(record['session_id'])):
                raise ValueError
            datetime.fromisoformat(record['ended_at'])
        except (ValueError, UnicodeError):
            record = None
            corrupt.append(number)
        rows.append([raw, record])
    return rows, corrupt


def _write_queue(rows, changed, environ=os.environ):
    path = queue_path(environ)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.kb-candidates-', dir=str(path.parent))
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as stream:
            for index, (raw, record) in enumerate(rows):
                if index in changed:
                    raw = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
                stream.write(raw)
                # A new row must not be joined to an unterminated existing row.
                if index < len(rows) - 1 and not raw.endswith(b'\n'):
                    stream.write(b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, UnicodeError, ValueError):
        raise CandidateError('无法写入候选队列，请检查路径与权限') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _identifier(session_id):
    return hashlib.sha256(session_id.encode('utf-8')).hexdigest()[:12]


def add(session_id, transcript_path, cwd, reason, environ=os.environ):
    if any(not isinstance(value, str) or not value.strip() or '\0' in value
           for value in (session_id, transcript_path, cwd, reason)):
        raise KbError('候选入队参数必须是非空字符串，且不能包含空字符')
    rows, corrupt = _read_queue(environ)
    index = next((index for index, (_, record) in enumerate(rows)
                  if record is not None and record['session_id'] == session_id), len(rows))
    old_status = rows[index][1]['status'] if index < len(rows) else 'pending'
    record = {'id': _identifier(session_id), 'session_id': session_id,
              'transcript_path': str(Path(transcript_path).expanduser().absolute()),
              'cwd': str(Path(cwd).expanduser().absolute()), 'reason': reason,
              'ended_at': datetime.now().astimezone().isoformat(),
              'status': 'pending' if old_status in ('pending', 'expired') else old_status}
    if index == len(rows):
        rows.append([b'', record])
    else:
        rows[index][1] = record
    _write_queue(rows, {index}, environ)
    return {'ok': True, 'candidate': record, 'corrupt_lines': corrupt}


def list_candidates(vault=None):
    vault = Vault.load() if vault is None else vault
    rows, corrupt = _read_queue()
    items = [{'kind': 'inbox', 'path': finding.path, 'reason': finding.message}
             for finding in inbox_backlog(vault)]
    changed, expired = set(), []
    now = datetime.now().astimezone()
    for index, (_, record) in enumerate(rows):
        if record is None or record['status'] in ('compiled', 'dropped'):
            continue
        if record['status'] == 'pending' and not Path(record['transcript_path']).is_file():
            record['status'] = 'expired'
            changed.add(index)
        if record['status'] == 'expired':
            expired.append(dict(record))
            continue
        ended_at = datetime.fromisoformat(record['ended_at']).astimezone()
        items.append({'kind': 'candidate', **record, 'expiring': now - ended_at > timedelta(days=25)})
    if changed:
        _write_queue(rows, changed)
    return {'ok': True, 'items': items, 'expired': expired, 'corrupt_lines': corrupt}


def _find(rows, identifier):
    for index, (_, record) in enumerate(rows):
        if record is not None and record['id'] == identifier:
            return index, record
    raise CandidateError('候选不存在：' + identifier)


def mark(identifier, status):
    if status not in ('compiled', 'dropped'):
        raise KbError('候选状态只允许 compiled 或 dropped')
    rows, corrupt = _read_queue()
    index, record = _find(rows, identifier)
    record['status'] = status
    _write_queue(rows, {index})
    return {'ok': True, 'candidate': record, 'corrupt_lines': corrupt}


# Host-injected blocks that arrive as user strings but were not typed by the user.
# <bash-input>/<bash-stdout> stay: they record commands the user ran themselves.
INJECTED_TAGS = ('system-reminder', 'task-notification', 'side-sessions-event')
INJECTED_RE = re.compile(r'<(%s)>.*?</\1>' % '|'.join(INJECTED_TAGS), re.DOTALL)


def _user_text(text):
    return html.unescape(INJECTED_RE.sub('', text))


def _extract(record):
    """Return text blocks and whether the record has an unknown structure.

    Only user and assistant records carry conversation. Every other record type
    (queue operations, attachments, titles, API request logs, snapshots, ...) is
    host metadata and is skipped silently, so the unknown count only reports
    conversation records whose shape this extractor does not understand.
    """
    if not isinstance(record, dict):
        return [], True
    kind = record.get('type')
    if kind not in ('user', 'assistant') or record.get('isSidechain') is True:
        return [], False
    if kind == 'user' and record.get('isMeta') is True:
        return [], False
    message = record.get('message')
    if not isinstance(message, dict):
        return [], True
    content = message.get('content')
    if kind == 'user' and isinstance(content, str):
        text = _user_text(content)
        return (['【用户】\n' + text] if text.strip() else []), False
    if not isinstance(content, list):
        return [], True
    texts, unknown = [], False
    for block in content:
        if not isinstance(block, dict):
            unknown = True
        elif block.get('type') == 'text' and isinstance(block.get('text'), str):
            if kind == 'assistant':
                texts.append('【助手】\n' + block['text'])
            else:
                text = _user_text(block['text'])
                if text.strip():
                    texts.append('【用户】\n' + text)
        elif block.get('type') not in ('tool_result', 'thinking', 'redacted_thinking', 'tool_use', 'image'):
            unknown = True
    return texts, unknown


def show(identifier, max_chars=40000):
    if type(max_chars) is not int or max_chars <= 0:
        raise KbError('候选查看用法错误：--max-chars 必须是正整数')
    blocklist = load_blocklist()
    rows, corrupt = _read_queue()
    index, record = _find(rows, identifier)
    if record['status'] == 'expired':
        raise CandidateError('会话记录已过期，无法查看；重新入队后再试')
    texts, skipped = [], 0
    try:
        with Path(record['transcript_path']).open('rb') as stream:
            for raw in stream:
                try:
                    parts, unknown = _extract(json.loads(raw.decode('utf-8')))
                except (ValueError, UnicodeError):
                    parts, unknown = [], True
                texts.extend(parts)
                skipped += int(unknown)
    except FileNotFoundError:
        record['status'] = 'expired'
        _write_queue(rows, {index})
        raise CandidateError('会话记录已过期或不存在，无法查看') from None
    except OSError:
        raise CandidateError('无法读取会话记录，请检查路径与权限') from None
    text = mask_text('\n\n'.join(texts), blocklist)
    truncated = max(0, len(text) - max_chars)
    if truncated:
        text = f'已截断前 {truncated} 字\n' + text[-max_chars:]
    text += f'\n\n跳过 {skipped} 条无法识别的记录。\n'
    return {'ok': True, 'text': text, 'skipped': skipped, 'corrupt_lines': corrupt}


def print_result(result, action, blocklist=()):
    for number in result.get('corrupt_lines', []):
        print(f'候选队列第 {number} 行损坏，已跳过。')
    if action == 'show':
        print(result['text'], end='')
    elif action in ('add', 'mark'):
        record = result['candidate']
        statuses = {'pending': '待处理', 'compiled': '已编译', 'dropped': '已丢弃', 'expired': '已过期'}
        print(f"候选 {record['id']}：{statuses[record['status']]}。")
    else:
        for item in result['items']:
            if item['kind'] == 'inbox':
                print('inbox 积压：' + mask_text(item['path'], blocklist))
            else:
                print(mask_text(f"候选 {item['id']}：{item['reason']}；{item['cwd']}；{item['ended_at']}"
                                + ('；即将过期' if item['expiring'] else ''), blocklist))
        for item in result['expired']:
            print(f"候选 {item['id']}：已过期。")
        print(f"待处理 {len(result['items'])} 项，已过期 {len(result['expired'])} 项。")
