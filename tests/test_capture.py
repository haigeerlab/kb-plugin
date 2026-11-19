import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from vault_support import CLI, ROOT


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / 'config dir/config.json'
        self.state = self.base / 'state'
        self.queue = self.state / 'candidates.jsonl'
        self.log = self.state / 'capture.log'
        self.vault = self.base / '知识库'
        self.vault.mkdir()
        (self.vault / 'keep.md').write_text('知识库原文', encoding='utf-8')
        self.env = dict(os.environ, KB_CONFIG=str(self.config), KB_STATE_DIR=str(self.state))
        self.transcript = self.base / 'session.jsonl'
        self.write_transcript([self.user('第一句'), self.user('第二句')])
        self.event = {'session_id': 'session-one', 'transcript_path': str(self.transcript),
                      'cwd': str(self.base), 'reason': 'prompt_input_exit'}
        self.write_config({'version': 1, 'vault': str(self.vault)})

    @staticmethod
    def user(content, **flags):
        return {'type': 'user', 'message': {'content': content}, **flags}

    def write_config(self, data):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def write_transcript(self, records):
        self.transcript.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records),
                                   encoding='utf-8')

    def run_cli(self, *args, stdin='', env=None):
        return subprocess.run([sys.executable, '-B', str(CLI), *args],
                              env=env or self.env, cwd=self.base, input=stdin, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def hook(self, event=None, stdin=None, *args):
        result = self.run_cli('capture', 'hook', *args,
                              stdin=json.dumps(self.event if event is None else event) if stdin is None else stdin)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''), result)
        return result

    def records(self):
        return [json.loads(line) for line in self.queue.read_text(encoding='utf-8').splitlines()] if self.queue.exists() else []

    def test_zero_one_two_user_messages_and_pointer_fields(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.write_transcript([self.user('用户原文不能入队')] * count)
                self.hook()
                self.assertEqual(len(self.records()), int(count == 2))
        row = self.records()[0]
        self.assertEqual(set(row), {'id', 'session_id', 'transcript_path', 'cwd', 'reason', 'ended_at', 'status'})
        for key in ('session_id', 'transcript_path', 'cwd', 'reason'):
            self.assertEqual(row[key], self.event[key])
        self.assertNotIn('用户原文', self.queue.read_text(encoding='utf-8'))

    def test_config_preview_confirm_and_preserve_other_fields(self):
        content = {'version': 1, 'vault': str(self.vault), 'custom': {'keep': [1, 2]}}
        self.write_config(content)
        before = self.config.read_bytes()
        args = ('config', 'set-capture', '--enabled', 'false', '--min-user-messages', '3',
                '--ignore-dir', '/a/b', '/space dir', '--json')
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertFalse(data['written'])
        expected = dict(content, session_capture=False, capture_min_user_messages=3,
                        capture_ignore_dirs=['/a/b', '/space dir'])
        self.assertEqual(data['content'], expected)
        self.assertEqual(self.config.read_bytes(), before)
        result = self.run_cli(*args, '--confirm')
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue(json.loads(result.stdout)['written'])
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')), expected)

    def test_status_defaults_and_pending_count(self):
        self.hook()
        result = self.run_cli('capture', 'status', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertTrue(data['session_capture'])
        self.assertEqual(data['capture_min_user_messages'], 2)
        self.assertEqual(data['capture_ignore_dirs'], [])
        self.assertEqual(data['pending'], 1)
        self.assertEqual(data['log_tail'], [])
        result = self.run_cli('capture', 'status')
        for text in ('开启', '阈值', '排除目录', '待处理', '不记录会话内容', 'config set-capture --enabled false'):
            self.assertIn(text, result.stdout)

    def test_bad_inputs_are_silent_and_logged(self):
        for stdin in ('', '{broken', '{}', '[]', 'null', json.dumps(dict(self.event, transcript_path='/nonexistent/session'))):
            with self.subTest(stdin=stdin):
                old = self.log.read_bytes() if self.log.exists() else b''
                self.hook(stdin=stdin)
                self.assertTrue(self.log.exists())
                self.assertGreater(self.log.stat().st_size, len(old))
                last = self.log.read_text(encoding='utf-8').splitlines()[-1]
                datetime.fromisoformat(last.split('\t')[0])
        self.assertEqual(self.records(), [])

    def test_injections_tools_meta_and_subagents_do_not_count(self):
        ignored = [self.user('注入', isMeta=True), self.user('子代理', isSidechain=True),
                   self.user([{'type': 'tool_result', 'content': '工具结果'}]),
                   self.user([{'type': 'image', 'source': {}}]), self.user('   '),
                   {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '助手'}]}},
                   {'type': 'system', 'message': {'content': '系统'}}]
        for tag in ('system-reminder', 'task-notification', 'side-sessions-event'):
            ignored.extend([self.user('<' + tag + '>注入</' + tag + '>'),
                            self.user([{'type': 'text', 'text': '<' + tag + '>注入</' + tag + '>'}])])
        self.write_transcript([self.user('一句真实输入')] + ignored * 50)
        self.hook()
        self.assertFalse(self.queue.exists())
        self.assertFalse(self.log.exists())
        with self.transcript.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(self.user([{'type': 'text', 'text': '第二句输入'}])) + '\n')
        self.hook()
        self.assertEqual(len(self.records()), 1)

    def test_multiple_text_blocks_count_as_one_message(self):
        self.write_transcript([self.user([{'type': 'text', 'text': '一'}, {'type': 'text', 'text': '二'}])])
        self.hook()
        self.assertEqual(self.records(), [])

    def test_threshold_is_configurable(self):
        for minimum in (1, 3):
            with self.subTest(minimum=minimum):
                self.write_config({'capture_min_user_messages': minimum})
                self.write_transcript([self.user('真实输入')] * (minimum - 1))
                self.hook()
                self.assertEqual(self.records(), [])
                self.write_transcript([self.user('真实输入')] * minimum)
                self.hook()
                self.assertEqual(len(self.records()), 1)
                self.queue.unlink()

    def test_ignore_directory_normalization_and_component_boundary(self):
        ignored = self.base / 'a/b'
        ignored.mkdir(parents=True)
        alias = self.base / 'alias'
        alias.symlink_to(ignored, target_is_directory=True)
        self.write_config({'capture_ignore_dirs': [str(self.base / 'other'), str(ignored) + '/./']})
        for cwd, excluded in ((ignored, True), (ignored / 'child', True),
                              (ignored / 'child/..', True), (alias / 'child', True),
                              (self.base / 'a/bc', False), (self.base / 'a', False)):
            with self.subTest(cwd=cwd):
                self.hook(event=dict(self.event, cwd=str(cwd)))
                self.assertEqual(bool(self.records()), not excluded)
                if self.queue.exists():
                    self.queue.unlink()

    def test_disabled_capture_returns_before_reading_transcript(self):
        self.write_config({'session_capture': False})
        self.transcript.unlink()
        self.hook()
        self.assertFalse(self.state.exists())

    def test_duplicate_session_updates_pointer_and_preserves_terminal_status(self):
        self.hook()
        self.hook(event=dict(self.event, reason='clear'))
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]['reason'], 'clear')
        for status in ('compiled', 'dropped'):
            record = dict(self.records()[0], status=status)
            self.queue.write_text(json.dumps(record) + '\n', encoding='utf-8')
            self.hook()
            self.assertEqual(len(self.records()), 1)
            self.assertEqual(self.records()[0]['status'], status)

    def test_every_required_field_is_validated_and_session_is_logged(self):
        for key in self.event:
            for value in (None, '', 3, '\0'):
                with self.subTest(key=key, value=value):
                    self.hook(event=dict(self.event, **{key: value}))
                    self.assertIn(key, self.log.read_text(encoding='utf-8').splitlines()[-1])
            event = dict(self.event)
            del event[key]
            self.hook(event=event)
        self.assertIn('session-one', self.log.read_text(encoding='utf-8'))
        self.assertFalse(self.queue.exists())

    def test_invalid_configurations_log_and_status_reports_two(self):
        invalid = ('{broken', '[]', 'null', '{"version": 2}',
                   '{"session_capture": "false"}', '{"session_capture": 0}',
                   '{"capture_min_user_messages": true}', '{"capture_min_user_messages": 0}',
                   '{"capture_min_user_messages": -1}', '{"capture_min_user_messages": 2.0}',
                   '{"capture_ignore_dirs": "/a"}', '{"capture_ignore_dirs": [null]}',
                   '{"capture_ignore_dirs": [""]}', '{"capture_ignore_dirs": ["\\u0000"]}')
        for content in invalid:
            with self.subTest(content=content):
                self.config.write_text(content, encoding='utf-8')
                before = self.log.stat().st_size if self.log.exists() else 0
                self.hook()
                self.assertGreater(self.log.stat().st_size, before)
                self.assertFalse(self.queue.exists())
                for flags in ((), ('--json',)):
                    result = self.run_cli('capture', 'status', *flags)
                    self.assertEqual(result.returncode, 2, result)
                    self.assertIn('配置', result.stdout + result.stderr)
                    self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_unreadable_configuration_and_transcript_are_silent(self):
        for path in (self.config, self.transcript):
            with self.subTest(path=path):
                before = path.read_bytes()
                path.write_bytes(b'\xff')
                self.hook()
                self.assertTrue(self.log.exists())
                self.assertEqual(self.records(), [])
                path.write_bytes(before)

    def test_readonly_state_directory_logs_to_existing_writable_log(self):
        # An existing writable log can still be appended in a read-only directory.
        self.state.mkdir()
        self.log.touch()
        self.state.chmod(0o555)
        try:
            self.hook()
            self.assertFalse(self.queue.exists())
            self.assertIn('无法写入候选队列', self.log.read_text(encoding='utf-8'))
        finally:
            self.state.chmod(0o755)

    def test_log_write_failure_is_also_silent(self):
        self.state.write_text('状态路径不是目录', encoding='utf-8')
        self.hook(stdin='')
        self.hook()
        self.assertEqual(self.state.read_text(encoding='utf-8'), '状态路径不是目录')

    def test_argument_errors_and_help_are_silent_and_logged(self):
        for args in (('--unknown',), ('extra',), ('--help',)):
            self.hook(None, None, *args)
            self.assertIn('采集入口失败', self.log.read_text(encoding='utf-8'))

    def test_missing_configuration_uses_defaults_without_creating_it(self):
        self.config.unlink()
        self.config.parent.rmdir()
        self.hook()
        self.assertEqual(len(self.records()), 1)
        result = self.run_cli('capture', 'status', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue(json.loads(result.stdout)['session_capture'])
        self.assertFalse(self.config.parent.exists())

    def test_large_transcript_finishes_under_one_second_and_stops_reading(self):
        self.transcript.write_bytes(self.transcript.read_bytes() + b'x' * (5 * 1024 * 1024))
        start = time.monotonic()
        self.hook()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)
        self.assertEqual(len(self.records()), 1)
        self.assertFalse(self.log.exists())
        from kblib import capture

        class EarlyStopStream(io.BytesIO):
            def __next__(stream):
                if stream.tell() >= len(prefix):
                    raise AssertionError('Transcript read after the second user message')
                return super().__next__()

        prefix = ('\n'.join(json.dumps(self.user('真实输入')) for _ in range(2)) + '\n').encode('utf-8')
        original_open = Path.open

        def open_path(path, *args, **kwargs):
            return EarlyStopStream(prefix) if path == self.transcript else original_open(path, *args, **kwargs)

        # Verify no iterator read is requested after the threshold, even at EOF.
        with patch.object(Path, 'open', open_path):
            capture.run_hook(json.dumps(dict(self.event, session_id='early-stop')), self.env)
        self.assertEqual(len(self.records()), 2)
        self.assertFalse(self.log.exists())

    def test_only_state_queue_and_log_change(self):
        (self.config.parent / 'other.txt').write_text('配置目录其他内容', encoding='utf-8')

        def snapshot(path):
            return {p.relative_to(path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in path.rglob('*') if p.is_file()}

        before = {p: snapshot(p) for p in (self.vault, self.config.parent)}
        self.hook()
        self.hook(stdin='')
        self.run_cli('capture', 'status')
        self.assertEqual({p: snapshot(p) for p in before}, before)
        self.assertEqual({p.name for p in self.state.iterdir()}, {'candidates.jsonl', 'capture.log'})

    def test_log_rotation_preserves_recent_lines_and_local_iso_timestamp(self):
        self.state.mkdir()
        self.log.write_text('旧记录\n' * 150000, encoding='utf-8')
        self.hook(stdin='')
        self.assertLess(self.log.stat().st_size, 1024 * 1024)
        text = self.log.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('旧记录\n'))
        last = text.splitlines()[-1]
        self.assertIn('JSONDecodeError', last)
        self.assertIsNotNone(datetime.fromisoformat(last.split('\t')[0]).tzinfo)

    def test_run_hook_uses_given_environment_and_never_prints(self):
        from kblib.capture import run_hook
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            run_hook(json.dumps(self.event), self.env)
            run_hook('', self.env)
        self.assertEqual((output.getvalue(), errors.getvalue()), ('', ''))
        self.assertEqual(len(self.records()), 1)
        self.assertTrue(self.log.exists())

    def test_status_lists_last_five_lines_and_does_not_expire_or_modify_queue(self):
        self.hook()
        record = self.records()[0]
        records = [dict(record, session_id=str(n), status=status) for n, status in enumerate(
            ('pending', 'compiled', 'dropped', 'expired'))]
        from kblib.candidates import _identifier
        for row in records:
            row['id'] = _identifier(row['session_id'])
        self.queue.write_text('坏行\n' + ''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
        self.log.write_text(''.join('日志 ' + str(n) + '\n' for n in range(8)), encoding='utf-8')
        self.transcript.unlink()
        before = {p: p.read_bytes() for p in (self.queue, self.log, self.config)}
        result = self.run_cli('capture', 'status', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(data['pending'], 1)
        self.assertEqual(data['corrupt_lines'], [1])
        self.assertEqual(data['log_tail'], ['日志 ' + str(n) for n in range(3, 8)])
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_set_capture_can_preserve_or_clear_options_and_validate_values(self):
        original = {'capture_min_user_messages': 4, 'capture_ignore_dirs': ['/a'], 'keep': True}
        self.write_config(original)
        result = self.run_cli('config', 'set-capture', '--enabled', 'true', '--json')
        data = json.loads(result.stdout)
        self.assertEqual(data['content']['capture_min_user_messages'], 4)
        self.assertEqual(data['content']['capture_ignore_dirs'], ['/a'])
        result = self.run_cli('config', 'set-capture', '--enabled', 'true', '--ignore-dir', '--json')
        self.assertEqual(json.loads(result.stdout)['content']['capture_ignore_dirs'], [])
        for args in (('--enabled', 'yes'), ('--enabled', 'true', '--min-user-messages', '0'),
                     ('--enabled', 'true', '--min-user-messages', '-1'),
                     ('--enabled', 'true', '--min-user-messages', 'abc'),
                     ('--enabled', 'true', '--ignore-dir', '')):
            with self.subTest(args=args):
                result = self.run_cli('config', 'set-capture', *args, '--confirm', '--json')
                self.assertEqual(result.returncode, 2, result)
                self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')), original)

    def test_set_capture_preview_creates_nothing_and_confirm_handles_write_failure(self):
        self.config.unlink()
        self.config.parent.rmdir()
        result = self.run_cli('config', 'set-capture', '--enabled', 'false')
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('--confirm', result.stdout)
        self.assertFalse(self.config.parent.exists())
        self.config.parent.write_text('无法作为目录', encoding='utf-8')
        result = self.run_cli('config', 'set-capture', '--enabled', 'false', '--confirm', '--json')
        self.assertEqual(result.returncode, 2, result)
        self.assertFalse(json.loads(result.stdout)['ok'])

    def test_draft_command_runs_verbatim_and_handles_missing_script_or_python(self):
        # The hook config ships as a draft first and is renamed to hooks.json once enabled;
        # test whichever one the repository currently carries.
        hooks_dir = ROOT / 'plugins/kb/hooks'
        draft = hooks_dir / 'hooks.json'
        if not draft.exists():
            draft = hooks_dir / 'hooks.json.draft'
        data = json.loads(draft.read_text(encoding='utf-8'))
        group = data['hooks']['SessionEnd'][0]
        self.assertNotIn('matcher', group)
        hook = group['hooks'][0]
        self.assertEqual(hook['type'], 'command')
        self.assertEqual(hook['timeout'], 5)
        command = hook['command']
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(CLI.parent.parent))
        for updates in ({}, {'CLAUDE_PLUGIN_ROOT': '', 'PLUGIN_ROOT': str(CLI.parent.parent)},
                        {'CLAUDE_PLUGIN_ROOT': str(self.base / 'missing')},
                        {'CLAUDE_PLUGIN_ROOT': '', 'PLUGIN_ROOT': ''}, {'PATH': '/nonexistent'}):
            with self.subTest(updates=updates):
                result = subprocess.run(['/bin/bash', '-c', command], env=dict(env, **updates),
                                        cwd=self.base, input=json.dumps(self.event), text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''), result)
                if not updates or updates.get('PLUGIN_ROOT') == str(CLI.parent.parent):
                    self.assertEqual(len(self.records()), 1)
                    self.queue.unlink()
                else:
                    self.assertFalse(self.queue.exists())


class CaptureManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.copy = self.base / 'copy'
        self.env = dict(os.environ, KB_CONFIG=str(self.base / 'config.json'), KB_STATE_DIR=str(self.base / 'state'))
        for relative in ('.claude-plugin/marketplace.json', 'plugins/kb/.claude-plugin/plugin.json',
                         'plugins/kb/.codex-plugin/plugin.json', 'plugins/kb/interface.json',
                         'plugins/kb/skills/ask/SKILL.md', 'plugins/kb/scripts/kb.py', 'scripts/check-manifests.py'):
            target = self.copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.draft = self.copy / 'plugins/kb/hooks/hooks.json.draft'
        self.draft.parent.mkdir(parents=True)
        self.data = {'hooks': {'SessionEnd': [{'hooks': [{'type': 'command', 'timeout': 5,
                     'command': 'python3 -B "$ROOT/scripts/kb.py" capture hook'}]}]}}

    def run_check(self):
        return subprocess.run([sys.executable, '-B', str(self.copy / 'scripts/check-manifests.py')],
                              cwd=self.base, env=self.env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)

    def write_draft(self):
        self.draft.write_text(json.dumps(self.data), encoding='utf-8')

    def test_optional_draft_or_live_hook_is_checked_in_temporary_copy(self):
        self.assertEqual(self.run_check().returncode, 0)
        self.write_draft()
        self.assertEqual(self.run_check().returncode, 0)
        live = self.draft.with_name('hooks.json')
        self.draft.rename(live)
        self.assertEqual(self.run_check().returncode, 0)
        self.write_draft()
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result)
        self.assertIn('同时', result.stderr)

    def test_invalid_hook_json_and_structure_are_rejected(self):
        for content in ('{broken', '[]', '{}', '{"hooks": {"Stop": []}}',
                        '{"hooks": {"SessionEnd": []}}', '{"hooks": {"SessionEnd": [null]}}',
                        '{"hooks": {"SessionEnd": [{"hooks": []}]}}'):
            with self.subTest(content=content):
                self.draft.write_text(content, encoding='utf-8')
                result = self.run_check()
                self.assertEqual(result.returncode, 1, result)
                self.assertNotIn('Traceback', result.stderr)

    def test_hook_requires_command_script_and_timeout_at_most_five(self):
        hook = self.data['hooks']['SessionEnd'][0]['hooks'][0]
        for key, value in (('type', 'prompt'), ('command', 'echo hello'), ('command', None),
                           ('timeout', 6), ('timeout', '5'), ('timeout', None),
                           ('timeout', True), ('timeout', 0)):
            with self.subTest(key=key, value=value):
                old = hook[key]
                hook[key] = value
                self.write_draft()
                result = self.run_check()
                self.assertEqual(result.returncode, 1, result)
                self.assertNotIn('Traceback', result.stderr)
                hook[key] = old
        self.write_draft()
        (self.copy / 'plugins/kb/scripts/kb.py').unlink()
        self.assertEqual(self.run_check().returncode, 1)

    def test_matcher_or_other_event_is_rejected(self):
        self.data['hooks']['SessionEnd'][0]['matcher'] = 'clear'
        self.write_draft()
        self.assertEqual(self.run_check().returncode, 1)
        del self.data['hooks']['SessionEnd'][0]['matcher']
        self.data['hooks']['Stop'] = []
        self.write_draft()
        self.assertEqual(self.run_check().returncode, 1)


if __name__ == '__main__':
    unittest.main()
