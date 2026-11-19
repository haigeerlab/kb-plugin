from datetime import datetime
import hashlib
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


class DelegateLessonsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.delegate = self.base / 'delegate'
        shutil.copytree(ROOT / 'tests/fixtures/delegate', self.delegate)
        for path in self.delegate.glob('*.result.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                continue
            data['answer']['path'] = str(self.delegate / Path(data['answer']['path']).name)
            path.write_text(json.dumps(data), encoding='utf-8')
        self.state = self.base / 'state'
        self.config = self.base / 'config.json'
        self.vault = self.base / 'vault'
        shutil.copytree(ROOT / 'tests/fixtures/vaults/valid', self.vault)
        self.settings = {'version': 1, 'vault': str(self.vault)}
        self.configure()
        self.env = dict(os.environ, KB_CONFIG=str(self.config), KB_STATE_DIR=str(self.state),
                        KB_DELEGATE_DIR=str(self.delegate))
        self.transcript = self.base / 'session.jsonl'
        self.transcript.write_text('', encoding='utf-8')
        self.event = {'session_id': 'session', 'transcript_path': str(self.transcript),
                      'cwd': str(self.base), 'reason': 'other'}

    def configure(self, **settings):
        self.settings.update(settings)
        self.config.write_text(json.dumps(self.settings), encoding='utf-8')

    def cli(self, *args, stdin=''):
        return subprocess.run([sys.executable, '-B', str(CLI), *args], env=self.env,
                              cwd=self.base, input=stdin, text=True, capture_output=True, timeout=5)

    def scan(self):
        result = self.cli('candidates', 'scan-delegate', '--json')
        self.assertEqual(result.returncode, 0, result)
        return json.loads(result.stdout)

    def snapshots(self):
        return {p.stem: json.loads(p.read_text(encoding='utf-8'))
                for p in (self.state / 'delegate').glob('*.json')}

    def records(self):
        path = self.state / 'candidates.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def clear_results(self):
        shutil.rmtree(self.delegate)
        self.delegate.mkdir()

    def result(self, run_id='run-000', answer='经验' * 120, **changes):
        data = json.loads((ROOT / 'tests/fixtures/delegate/20261118080000.1001.result.json').read_text())
        answer_path = self.delegate / (run_id + '.answer')
        answer_path.write_text(answer, encoding='utf-8')
        data.update(runId=run_id, chainRoot=run_id, answer={'path': str(answer_path), 'bytes': 0})
        data.update(changes)
        self.write_result(run_id, data)
        return data

    def write_result(self, run_id, data):
        (self.delegate / (run_id + '.result.json')).write_text(json.dumps(data), encoding='utf-8')

    def test_fixture_filtering_readonly_incremental_and_scan_status(self):
        def hashes():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.delegate.iterdir()}
        before = hashes()
        data = self.scan()
        self.assertEqual((data['collected'], data['skipped'], data['processed']), (5, 6, 11))
        expected = {'20261118080000.' + n for n in ('1001', '1003', '1006', '1007', '1008')}
        self.assertEqual(set(self.snapshots()), expected)
        self.assertEqual(len(self.records()), 5)
        self.assertTrue(all(r['source'] == 'delegate' for r in self.records()))
        self.assertEqual({i['runId'] for i in data['items'] if i['action'] == 'collected'}, expected)
        self.assertTrue(all(i['reason'] for i in data['items']))
        self.assertNotIn('answer', data)
        log = (self.state / 'capture.log').read_text(encoding='utf-8')
        for suffix in ('1009', '1010', '1011'):
            self.assertIn(suffix, log)
        status = json.loads(self.cli('capture', 'status', '--json').stdout)
        self.assertTrue(status['delegate_capture'])
        self.assertEqual(status['delegate_min_answer_bytes'], 200)
        datetime.fromisoformat(status['delegate_last_scan_at'])
        self.assertEqual(status['delegate_last_scan_processed'], 11)
        snapshot_bytes = {p: p.read_bytes() for p in (self.state / 'delegate').iterdir()}
        second = self.scan()
        self.assertEqual((second['collected'], second['skipped'], second['processed']), (0, 0, 0))
        self.assertEqual(second['items'], [])
        self.assertEqual(len(self.records()), 5)
        self.assertEqual({p: p.read_bytes() for p in snapshot_bytes}, snapshot_bytes)
        self.assertEqual(hashes(), before)

    def test_threshold_uses_actual_utf8_bytes_and_is_configurable(self):
        self.clear_results()
        self.configure(delegate_min_answer_bytes=6)
        self.result('short', answer='经')
        self.result('boundary', answer='经验')
        self.result('failure', answer='', commands=[{'command': '失败', 'exitCode': 1}])
        self.assertEqual(self.scan()['collected'], 2)
        self.assertEqual(set(self.snapshots()), {'boundary', 'failure'})

    def test_snapshot_fields_and_character_limits(self):
        self.clear_results()
        original = self.result(answer='经验' * 11000, commands=[
            {'command': '成' * 500, 'exitCode': 0},
            {'command': '败' * 500, 'exitCode': 2},
            {'command': '超时', 'exitCode': None}])
        self.scan()
        snapshot = self.snapshots()['run-000']
        self.assertEqual(set(snapshot), {'runId', 'status', 'repository', 'write', 'startedAt',
                                        'endedAt', 'changedFiles', 'failedCommands', 'answer'})
        for key in ('runId', 'status', 'repository', 'write', 'startedAt', 'endedAt', 'changedFiles'):
            self.assertEqual(snapshot[key], original[key])
        self.assertEqual(snapshot['answer'], ('经验' * 11000)[:20000])
        self.assertEqual(snapshot['failedCommands'], [{'command': '败' * 300, 'exitCode': 2},
                                                      {'command': '超时', 'exitCode': None}])

    def test_chain_chooses_last_end_time_and_never_collects_later_arrival(self):
        self.clear_results()
        self.result('z-earlier', chainRoot='chain', endedAt='2026-11-18T09:00:00Z')
        self.result('a-later', chainRoot='chain', endedAt='2026-11-18T11:00:00+01:00')
        self.result('waiting', chainRoot='other', status='needs-input')
        self.assertEqual(self.scan()['collected'], 1)
        self.assertEqual(set(self.snapshots()), {'a-later'})
        self.result('new-later', chainRoot='chain', endedAt='2026-11-18T12:00:00Z')
        self.result('resumed', chainRoot='other')
        self.assertEqual(self.scan()['collected'], 1)
        self.assertEqual(set(self.snapshots()), {'a-later', 'resumed'})

    def test_twenty_result_limit_and_chain_selection_across_batch_boundary(self):
        self.clear_results()
        for n in range(25):
            self.result(f'run-{n:03}')
        first = self.scan()
        self.assertEqual((first['processed'], first['collected']), (20, 20))
        self.assertEqual([i['runId'] for i in first['items']], [f'run-{n:03}' for n in range(20)])
        self.assertEqual(self.scan()['processed'], 5)
        self.assertEqual(len(self.snapshots()), 25)

    def test_chain_latest_outside_first_twenty_is_not_lost(self):
        self.clear_results()
        for n in range(25):
            self.result(f'run-{n:03}', chainRoot='chain', endedAt=f'2026-11-18T08:{n:02}:00Z')
        self.assertEqual(self.scan()['collected'], 0)
        self.assertEqual(self.scan()['collected'], 1)
        self.assertEqual(set(self.snapshots()), {'run-024'})

    def test_sorting_uses_run_id_instead_of_result_filename(self):
        self.clear_results()
        run_ids = ['a.b', 'aa', 'a-1', 'a']
        for run_id in run_ids:
            self.result(run_id)
        self.assertEqual([item['runId'] for item in self.scan()['items']], sorted(run_ids))

    def test_ended_statuses_only(self):
        self.clear_results()
        for status in ('done', 'failed', 'timeout', 'unmarked', 'unreaped', 'empty', 'needs-input', 'interrupted'):
            self.result(status, status=status)
        self.assertEqual(self.scan()['collected'], 6)

    def test_invalid_fields_and_schema_are_logged_not_raised(self):
        self.clear_results()
        changes = ({'schema': True}, {'schema': 2}, {'runId': '../escape'}, {'commands': [None]},
                   {'commands': [{}]}, {'answer': None}, {'write': 1}, {'endedAt': 'bad'},
                   {'changedFiles': None}, {'repository': None}, {'chainRoot': None})
        for n, change in enumerate(changes):
            run_id = f'bad-{n:03}'
            data = self.result(run_id)
            data.update(change)
            self.write_result(run_id, data)
        missing = self.result('missing')
        del missing['startedAt']
        self.write_result('missing', missing)
        (self.delegate / 'broken.result.json').write_text('{broken')
        (self.delegate / 'array.result.json').write_text('[]')
        self.assertEqual((self.scan()['collected'], len(self.snapshots())), (0, 0))
        self.assertEqual(self.scan()['processed'], 0)
        self.assertIn('missing', (self.state / 'capture.log').read_text())

    def test_nonexistent_directory_logs_and_returns_zero(self):
        self.env['KB_DELEGATE_DIR'] = str(self.base / 'missing')
        data = self.scan()
        self.assertEqual(data['processed'], 0)
        self.assertIn('目录', (self.state / 'capture.log').read_text())

    def test_existing_snapshot_is_not_reprocessed(self):
        self.clear_results()
        self.result()
        target = self.state / 'delegate/run-000.json'
        target.parent.mkdir(parents=True)
        target.write_text('{}')
        self.assertEqual(self.scan()['processed'], 0)
        self.assertEqual(target.read_text(), '{}')
        self.assertEqual(self.records(), [])

    def test_list_show_redaction_mark_and_legacy_session(self):
        self.clear_results()
        secret = 'ghp_' + 'a2B' * 12
        self.result(answer='发现 ' + secret + ' 客户名称 解法', commands=[{'command': secret, 'exitCode': 1}])
        (self.base / 'blocklist.txt').write_text('客户名称\n', encoding='utf-8')
        self.scan()
        record = self.records()[0]
        listing = self.cli('candidates', 'list')
        self.assertEqual(listing.returncode, 0, listing)
        for text in ('repo-a', 'done', '2026-11-18'):
            self.assertIn(text, listing.stdout)
        result = self.cli('candidates', 'show', record['id'])
        self.assertEqual(result.returncode, 0, result)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn('客户名称', result.stdout)
        self.assertIn('ghp_' + '*' * 36, result.stdout)
        self.assertIn('failedCommands', result.stdout)
        self.assertIn('已截断', self.cli('candidates', 'show', record['id'], '--max-chars', '30').stdout)
        self.assertEqual(self.cli('candidates', 'mark', record['id'], '--status', 'dropped').returncode, 0)
        legacy = {'id': hashlib.sha256(b'legacy').hexdigest()[:12], 'session_id': 'legacy',
                  'transcript_path': str(self.transcript), 'cwd': str(self.base), 'reason': '旧记录',
                  'ended_at': datetime.now().astimezone().isoformat(), 'status': 'pending'}
        self.transcript.write_text(json.dumps({'type': 'user', 'message': {'content': '旧会话'}}) + '\n')
        with (self.state / 'candidates.jsonl').open('a') as stream:
            stream.write(json.dumps(legacy) + '\n')
        before = (self.state / 'candidates.jsonl').read_bytes()
        listing = json.loads(self.cli('candidates', 'list', '--json').stdout)
        self.assertEqual([i['source'] for i in listing['items'] if i['kind'] == 'candidate'], ['session'])
        self.assertIn('旧会话', self.cli('candidates', 'show', legacy['id']).stdout)
        self.assertEqual((self.state / 'candidates.jsonl').read_bytes(), before)

    def test_hook_runs_independently_of_session_threshold_and_switch(self):
        self.configure(session_capture=False)
        result = self.cli('capture', 'hook', stdin=json.dumps(self.event))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual(len(self.snapshots()), 5)
        shutil.rmtree(self.state)
        self.configure(delegate_capture=False)
        result = self.cli('capture', 'hook', stdin=json.dumps(self.event))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertFalse(self.state.exists())

    def test_hook_bad_inputs_and_scan_exceptions_are_silent(self):
        for content in ('', '{}', '[]', '{broken', json.dumps(self.event)):
            with self.subTest(content=content):
                result = self.cli('capture', 'hook', stdin=content)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        from kblib import capture
        import contextlib
        import io
        output, errors = io.StringIO(), io.StringIO()
        with patch('kblib.delegate_lessons.scan', side_effect=RuntimeError), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            capture.run_hook(json.dumps(self.event), self.env)
        self.assertEqual((output.getvalue(), errors.getvalue()), ('', ''))
        self.assertIn('RuntimeError', (self.state / 'capture.log').read_text())

    def test_hook_two_hundred_results_twenty_new_under_one_second(self):
        self.clear_results()
        for n in range(180):
            self.result(f'run-{n:03}')
        for _ in range(9):
            self.scan()
        for n in range(180, 200):
            self.result(f'run-{n:03}')
        before = len(self.records())
        hook = json.loads((ROOT / 'plugins/kb/hooks/hooks.json').read_text())['hooks']['SessionEnd'][0]['hooks'][0]
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(CLI.parent.parent))
        start = time.monotonic()
        result = subprocess.run(['/bin/bash', '-c', hook['command']], env=env, input=json.dumps(self.event),
                                text=True, capture_output=True, cwd=self.base, timeout=5)
        elapsed = time.monotonic() - start
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertLess(elapsed, 1.0)
        self.assertEqual(len(self.records()) - before, 20)

    def test_invalid_delegate_config_is_rejected_and_hook_stays_silent(self):
        for changes in ({'delegate_capture': 'false'}, {'delegate_min_answer_bytes': True},
                        {'delegate_min_answer_bytes': -1}, {'delegate_min_answer_bytes': 1.5}):
            self.settings = {'version': 1, 'vault': str(self.vault)}
            self.configure(**changes)
            self.assertEqual(self.cli('capture', 'status', '--json').returncode, 2)
            result = self.cli('capture', 'hook', stdin=json.dumps(self.event))
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_delegate_inbox_compile_and_contract_check_in_temporary_vault(self):
        def git(*args):
            result = subprocess.run(['git', '-C', str(self.vault), '-c', 'core.hooksPath=/dev/null',
                                     '-c', 'commit.gpgsign=false', *args], env=self.env,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result)
            return result.stdout

        git('init', '-q')
        git('config', 'user.name', 'Delegate Lessons Tests')
        git('config', 'user.email', 'delegate@example.invalid')
        git('add', '.')
        git('commit', '-qm', '测试知识库基线')
        self.clear_results()
        self.result(answer='当前方法已经验证。' * 30)
        self.scan()
        shown = self.cli('candidates', 'show', self.records()[0]['id'])
        self.assertIn('当前方法已经验证。', shown.stdout)
        draft = self.base / 'draft'
        (draft / 'inbox').mkdir(parents=True)
        (draft / 'inbox/2026-01-02-delegate.md').write_text(
            '---\ncaptured: 2026-01-02\nsource: delegate\nhost: codex\ntitle: 执行经验\n---\n'
            '# 执行经验\n\n当前方法已经验证。\n', encoding='utf-8')
        (draft / 'log.md').write_text((self.vault / 'log.md').read_text(encoding='utf-8')
                                     + '\n## [2026-01-02] compile | 执行经验\n\n整理执行经验。\n', encoding='utf-8')
        preview = self.cli('compile', 'preview', str(draft), '--json')
        self.assertEqual(preview.returncode, 0, preview)
        fingerprint = json.loads(preview.stdout)['fingerprint']
        applied = self.cli('compile', 'apply', str(draft), '--confirm', fingerprint, '--json')
        self.assertEqual(applied.returncode, 0, applied)
        checked = self.cli('check', '--json')
        self.assertEqual(checked.returncode, 0, checked)
        self.assertEqual(json.loads(checked.stdout)['findings'], [])
        self.assertEqual(git('log', '-1', '--format=%s').strip(), 'compile: 执行经验')

    def test_empty_manual_scan_records_zero_and_status_is_readonly(self):
        self.clear_results()
        self.assertEqual(self.scan()['processed'], 0)
        before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        status = self.cli('capture', 'status', '--json')
        self.assertEqual(status.returncode, 0, status)
        data = json.loads(status.stdout)
        datetime.fromisoformat(data['delegate_last_scan_at'])
        self.assertEqual(data['delegate_last_scan_processed'], 0)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_disabled_manual_scan_and_zero_threshold(self):
        self.clear_results()
        self.result(answer='')
        self.configure(delegate_capture=False)
        self.assertEqual(self.scan()['processed'], 0)
        self.assertFalse(self.state.exists())
        self.configure(delegate_capture=True, delegate_min_answer_bytes=0)
        self.assertEqual(self.scan()['collected'], 1)

    def test_queue_failure_retries_without_leaving_an_orphan_snapshot(self):
        from kblib import delegate_lessons, KbError
        self.clear_results()
        self.result()
        with patch('kblib.candidates.add_delegate', side_effect=KbError('测试写入失败')):
            data = delegate_lessons.scan(self.env)
        self.assertEqual((data['collected'], data['skipped']), (0, 1))
        self.assertEqual(self.snapshots(), {})
        self.assertEqual(self.scan()['collected'], 1)

    def test_overlapping_state_directory_does_not_modify_delegate(self):
        self.env['KB_STATE_DIR'] = str(self.delegate / 'state')
        before = {p: p.read_bytes() for p in self.delegate.iterdir() if p.is_file()}
        data = self.scan()
        self.assertEqual(data['processed'], 0)
        self.assertIn('只读', data['reason'])
        self.assertFalse((self.delegate / 'state').exists())
        self.assertEqual({p: p.read_bytes() for p in before}, before)


if __name__ == '__main__':
    unittest.main()
