"""Read delegate's public results into local, incremental lesson candidates."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from . import candidates
from .config import load_capture


ENDED = ('done', 'failed', 'timeout', 'unmarked', 'unreaped', 'empty')
LIMIT = 20


def _log(reason, environ, run_id=None):
    from .capture import log_error
    log_error('delegate' + (' ' + run_id if run_id else '') + '：' + reason, environ)


def _state_path(environ):
    return candidates.queue_path(environ).parent / 'delegate-scan.json'


def _load_state(environ, log_errors=True):
    empty = {'processed': {}, 'chains': {}, 'last_scan_at': None, 'last_scan_processed': 0}
    try:
        data = json.loads(_state_path(environ).read_text(encoding='utf-8'))
        if (not isinstance(data, dict)
                or any(not isinstance(data.get(key), dict)
                       or any(not isinstance(k, str) or not isinstance(v, str)
                              for k, v in data[key].items()) for key in ('processed', 'chains'))
                or type(data.get('last_scan_processed')) is not int):
            raise ValueError
        datetime.fromisoformat(data['last_scan_at'])
        return data
    except FileNotFoundError:
        return empty
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
        if log_errors:
            _log('扫描状态无法读取或已损坏', environ)
        return empty


def scan_status(environ=os.environ):
    state = _load_state(environ, log_errors=False)
    return {'delegate_last_scan_at': state['last_scan_at'],
            'delegate_last_scan_processed': state['last_scan_processed']}


def _write_json(path, data):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.kb-delegate-', dir=str(path.parent))
        temporary = Path(name)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _result(path, run_id):
    """Validate only the public fields we consume; never include input in errors."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None, '结果 JSON 损坏或无法读取'
    if not isinstance(data, dict):
        return None, '结果必须是 JSON 对象'
    if type(data.get('schema')) is not int or data['schema'] != 1:
        return None, '不支持的 schema（仅支持整数 1）'
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', run_id)
            or data.get('runId') != run_id):
        return None, 'runId 缺失、无效或与文件名不一致'
    if data.get('kind') == 'review':
        return None, 'review 不收集'
    if data.get('kind') != 'run':
        return None, 'kind 缺失或不是 run'
    if data.get('status') not in ENDED:
        return None, '状态未结束或不在收集范围'
    try:
        for key in ('chainRoot', 'repository', 'startedAt', 'endedAt'):
            if not isinstance(data[key], str) or not data[key].strip() or '\0' in data[key]:
                raise ValueError
        _timestamp(data['startedAt'])
        _timestamp(data['endedAt'])
        if (type(data['write']) is not bool or not isinstance(data['changedFiles'], list)
                or any(not isinstance(value, str) for value in data['changedFiles'])
                or not isinstance(data['commands'], list)
                or any(not isinstance(command, dict) or not isinstance(command.get('command'), str)
                       or 'exitCode' not in command
                       or (command['exitCode'] is not None and type(command['exitCode']) is not int)
                       for command in data['commands'])
                or not isinstance(data['answer'], dict)
                or not isinstance(data['answer'].get('path'), str)
                or not data['answer']['path'] or '\0' in data['answer']['path']):
            raise ValueError
    except (KeyError, ValueError, TypeError, OverflowError):
        return None, '结果字段缺失或格式无效'
    return data, None


def scan(environ=os.environ, *, record_empty=True):
    settings = load_capture(environ)
    result = {'ok': True, 'collected': 0, 'skipped': 0, 'processed': 0, 'items': []}
    if not settings['delegate_capture']:
        result['reason'] = 'delegate_capture 已关闭'
        return result
    directory = Path(environ.get('KB_DELEGATE_DIR')
                     or str(Path(environ.get('TMPDIR') or '/tmp') / 'delegate')).expanduser()
    state_dir = candidates.queue_path(environ).parent
    # Even an explicitly overlapping override must not write into delegate's directory.
    if state_dir.resolve().is_relative_to(directory.resolve()):
        result['reason'] = '状态目录位于 delegate 目录内，已跳过以保持只读'
        return result
    try:
        paths = sorted((path for path in directory.iterdir() if path.name.endswith('.result.json')),
                       key=lambda path: path.name[:-len('.result.json')])
    except OSError:
        paths = []
        _log('结果目录不存在或无法读取', environ)
    # A hook with nothing to inspect remains a no-op, including on fresh installations.
    if not paths and not record_empty:
        return result
    state = _load_state(environ)
    snapshots = state_dir / 'delegate'
    new, latest = [], {}
    for path in paths:
        run_id = path.name[:-len('.result.json')]
        if run_id in state['processed']:
            continue
        data, reason = _result(path, run_id)
        if (snapshots / (run_id + '.json')).exists():
            if data is not None:
                state['chains'][data['chainRoot']] = run_id
            continue
        new.append((run_id, data, reason))
        if data is not None:
            key = (_timestamp(data['endedAt']), run_id)
            root = data['chainRoot']
            if root not in latest or key > latest[root]:
                latest[root] = key
    for run_id, data, reason in new[:LIMIT]:
        if data is not None:
            root = data['chainRoot']
            if root in state['chains']:
                reason = '同一 chainRoot 已收集'
            elif latest[root][1] != run_id:
                reason = '同一链有更晚结束的 run'
            else:
                try:
                    with Path(data['answer']['path']).open(encoding='utf-8') as stream:
                        byte_count = os.fstat(stream.fileno()).st_size
                        answer = stream.read(20000)
                except (OSError, UnicodeError, ValueError):
                    reason = '答复文件缺失或无法读取'
                else:
                    failed = [{'command': command['command'][:300], 'exitCode': command['exitCode']}
                              for command in data['commands'] if command['exitCode'] != 0]
                    if byte_count < settings['delegate_min_answer_bytes'] and not failed:
                        reason = '答复低于字节阈值且命令全部成功'
                    else:
                        snapshot = {key: data[key] for key in ('runId', 'status', 'repository', 'write',
                                                               'startedAt', 'endedAt', 'changedFiles')}
                        snapshot.update(failedCommands=failed, answer=answer)
                        target = snapshots / (run_id + '.json')
                        try:
                            _write_json(target, snapshot)
                            candidates.add_delegate(snapshot, target, environ)
                        except Exception as error:
                            target.unlink(missing_ok=True)
                            _log('快照入队失败：' + type(error).__name__, environ, run_id)
                            # Retry state/queue write failures on the next scan.
                            result['items'].append({'runId': run_id, 'action': 'skipped',
                                                    'reason': '快照或候选写入失败，留待重试'})
                            result['skipped'] += 1
                            result['processed'] += 1
                            continue
                        state['chains'][root] = run_id
        action = 'skipped' if reason else 'collected'
        result[action] += 1
        result['processed'] += 1
        reason = reason or '已保存快照并入队'
        result['items'].append({'runId': run_id, 'action': action, 'reason': reason})
        state['processed'][run_id] = reason
        if action == 'skipped':
            _log(reason, environ, run_id)
    state.update(last_scan_at=datetime.now().astimezone().isoformat(),
                 last_scan_processed=result['processed'])
    try:
        _write_json(_state_path(environ), state)
    except (OSError, UnicodeError, ValueError):
        _log('无法写入扫描状态', environ)
    return result


def print_result(result, blocklist=()):
    from .redaction import mask_text
    print(f"收集 {result['collected']} 个，跳过 {result['skipped']} 个；处理 {result['processed']} 个新结果。")
    if result.get('reason'):
        print(result['reason'])
    for item in result['items']:
        label = '收集' if item['action'] == 'collected' else '跳过'
        print(mask_text(f"{item['runId']}：{label}；{item['reason']}", blocklist))
