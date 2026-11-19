"""Silent SessionEnd capture of local candidate pointers."""

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path

from . import KbError, candidates
from .config import load_capture


LOG_LIMIT = 1024 * 1024


def log_error(reason, environ, session_id=None):
    """Logging must never prevent the host from ending its session."""
    try:
        path = candidates.queue_path(environ).parent / 'capture.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        line = datetime.now().astimezone().isoformat() + '\t' + str(reason).replace('\n', ' ').replace('\r', ' ')
        if session_id is not None:
            line += '\t会话=' + json.dumps(session_id, ensure_ascii=False)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
        size = path.stat().st_size
        if size > LOG_LIMIT:
            with path.open('rb') as stream:
                stream.seek(size // 2)
                tail = stream.read().partition(b'\n')[2]
            path.write_bytes(tail)
    except BaseException:
        pass


def run_hook(stdin_text, environ):
    session_id = None
    try:
        event = json.loads(stdin_text)
        if not isinstance(event, dict):
            raise KbError('SessionEnd 输入必须是 JSON 对象')
        session_id = event.get('session_id')
        for key in ('session_id', 'transcript_path', 'cwd', 'reason'):
            value = event.get(key)
            if not isinstance(value, str) or not value.strip() or '\0' in value:
                raise KbError('SessionEnd 缺少有效字段：' + key)
        settings = load_capture(environ)
        if not settings['session_capture']:
            return
        cwd = Path(event['cwd']).expanduser().resolve()
        for value in settings['capture_ignore_dirs']:
            ignored = Path(value).expanduser().resolve()
            if cwd == ignored or ignored in cwd.parents:
                return
        count = 0
        with Path(event['transcript_path']).expanduser().open('rb') as stream:
            for raw in stream:
                record = json.loads(raw.decode('utf-8'))
                if isinstance(record, dict) and record.get('type') == 'user':
                    texts, _ = candidates._extract(record)
                    count += bool(texts)
                    if count >= settings['capture_min_user_messages']:
                        break
        if count >= settings['capture_min_user_messages']:
            candidates.add(session_id, event['transcript_path'], event['cwd'], event['reason'], environ=environ)
    except BaseException as error:
        reason = str(error) if isinstance(error, KbError) else '采集失败：' + type(error).__name__
        log_error(reason, environ, session_id)


def status(environ=os.environ):
    settings = load_capture(environ)
    try:
        rows, corrupt = candidates._read_queue(environ)
        path = candidates.queue_path(environ).parent / 'capture.log'
        try:
            with path.open(encoding='utf-8') as stream:
                tail = [line.rstrip('\n') for line in deque(stream, maxlen=5)]
        except FileNotFoundError:
            tail = []
    except (OSError, UnicodeError, KbError):
        raise KbError('无法读取采集状态，请检查候选队列与日志的路径和权限') from None
    return {'ok': True, **settings,
            'pending': sum(record is not None and record['status'] == 'pending' for _, record in rows),
            'corrupt_lines': corrupt, 'log': str(path), 'log_tail': tail,
            'notice': '只记录会话 ID、记录路径、工作目录与结束原因，不记录会话内容。'
                      '关闭：kb.py config set-capture --enabled false --confirm；hook 需启用后才生效。'}


def print_status(result):
    print('会话结束采集：' + ('开启' if result['session_capture'] else '关闭'))
    print(f"用户消息阈值：{result['capture_min_user_messages']}")
    print('排除目录：' + ('、'.join(result['capture_ignore_dirs']) or '无'))
    print(f"待处理候选：{result['pending']}；日志：{result['log']}")
    for line in result['log_tail']:
        print(line)
    print(result['notice'])
